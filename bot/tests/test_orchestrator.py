from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from backtest.engine.structure import Direction
from backtest.engine.trade_log import TradeRecord

from .fake_mt5 import FakeMT5, make_position, make_symbol_info, make_deal
from ..audit_log import AuditLog, DecisionRecord
from ..config import AccountProfile, MT5Credentials, PhaseConfig, PhaseRules
from ..mt5_data import MT5Client, MT5ConnectionError
from ..mt5_execution import MT5Execution
from ..orchestrator import RECONNECT_BACKOFF_BASE_SECONDS, LiveBot, TrackedPosition

RULES = PhaseRules(daily_dd_limit_pct=0.04, overall_dd_limit_pct=0.10,
                    risk_normal=1000.0, risk_reduced=500.0, de_risk_at_pct=0.05,
                    profit_target_pct=0.08)
CREDS = MT5Credentials(login=1, password="pw", server="Demo")


def make_profile():
    return AccountProfile(account_type="prop_firm", active_phase="phase1",
                           phases={"phase1": PhaseConfig(rules=RULES, credentials=CREDS)})


def make_bot(fake, tmp_path, instruments=("EURUSD",)):
    fake.symbols.setdefault("EURUSD", make_symbol_info(point=0.0001))
    client = MT5Client(fake, login=1, password="pw", server="Demo", server_utc_offset=pd.Timedelta(0))
    client.connect()
    execu = MT5Execution(fake)
    audit = AuditLog(str(tmp_path / "audit.db"))
    return LiveBot(profile=make_profile(), mt5_client=client, mt5_exec=execu,
                    audit_log=audit, instruments=instruments), audit, client


@contextmanager
def gate_open():
    """Hold the storyline gate open.

    The gate itself (Daily/H4 alignment -> is this pair even worth an H1
    search) is covered in test_live_strategy.py, including against real
    cached history. These orchestrator tests are about what happens once
    an instrument IS being hunted, so holding it open keeps them focused
    on that -- and independent of whether real candle data happens to be
    present, which is gitignored and absent on a clean checkout."""
    with patch.object(LiveBot, "_storyline_says_hunt", return_value=True):
        yield


def a_trade_record(entry_time, trade_id=1, direction=Direction.BULLISH):
    return TradeRecord(
        trade_id=trade_id, instrument="EURUSD", entry_time=entry_time,
        direction=direction, entry_timeframe="H1", entry_price=1.17374,
        stop_loss=1.17290, primary_target=1.17626,
        trigger_type="engulfing",
        bias_weekly=Direction.BULLISH, aligned_timeframes="Weekly,Daily,H4",
        status="open",
    )


# ---- health / connectivity ----

def test_run_once_does_nothing_when_mt5_is_unhealthy(tmp_path):
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    client.disconnect()  # not healthy anymore
    fake._fail_init = True  # reconnect attempt also fails, cleanly

    bot.run_once()
    assert audit.recent(10) == []


# ---- reconnect backoff ----

def test_the_first_reconnect_attempt_after_going_unhealthy_is_immediate(tmp_path):
    # No regression for the common case: a one-off blip must still
    # recover on the very next poll, exactly as before backoff existed.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)  # make_bot's own setup already did one connect()
    client.disconnect()
    fake.initialize_calls = 0

    bot._try_reconnect()

    assert fake.initialize_calls == 1
    assert client.is_healthy()


def test_repeated_failures_are_not_retried_on_every_single_poll(tmp_path):
    # Confirmed live 2026-08-27/28: 150 and 158 consecutive
    # mt5.initialize() failures, one every flat 5 seconds, no backoff --
    # 12+ minutes of IPC calls against an already-failing terminal on a
    # resource-contended VPS. A second call made immediately after a
    # failure (well inside the backoff window) must not attempt another
    # real connect() at all.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    client.disconnect()
    fake._fail_init = True
    fake.initialize_calls = 0

    bot._try_reconnect()  # attempt 1: fails, starts the backoff window
    assert fake.initialize_calls == 1

    bot._try_reconnect()  # called again immediately -- still inside the window
    assert fake.initialize_calls == 1  # no second attempt yet


def test_the_backoff_delay_grows_and_is_capped(tmp_path):
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    client.disconnect()
    fake._fail_init = True
    fake.initialize_calls = 0

    delays = []
    for _ in range(7):
        bot._try_reconnect()
        # Force the next call past the just-set backoff window, as if
        # that much wall-clock time had actually elapsed.
        delays.append((bot._next_reconnect_at - datetime.now(timezone.utc)).total_seconds())
        bot._next_reconnect_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert fake.initialize_calls == 7
    # 5, 10, 20, 40, 60, 60, 60 -- doubles from the base, capped at max.
    rounded = [round(d) for d in delays]
    assert rounded[:5] == [5, 10, 20, 40, 60]
    assert rounded[5] == 60 and rounded[6] == 60


def test_a_successful_reconnect_resets_the_backoff(tmp_path):
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    client.disconnect()
    fake._fail_init = True

    bot._try_reconnect()
    bot._try_reconnect()  # still failing -- attempt count and delay have grown
    assert bot._reconnect_attempts == 1  # second call was inside the window, didn't even try

    bot._next_reconnect_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    fake._fail_init = False  # the terminal recovers
    bot._try_reconnect()

    assert bot._reconnect_attempts == 0
    assert bot._next_reconnect_at is None

    # A LATER failure must start the backoff over from the base delay,
    # not continue from wherever the previous outage left off.
    client.disconnect()
    fake._fail_init = True
    bot._try_reconnect()
    delay = (bot._next_reconnect_at - datetime.now(timezone.utc)).total_seconds()
    assert round(delay) == RECONNECT_BACKOFF_BASE_SECONDS


def test_resource_snapshot_is_logged_once_per_outage_not_per_attempt(tmp_path, caplog):
    # Direct 2026-08-29 request: settle whether the recurring "Terminal:
    # Authorization failed" outages are VPS-side (resource contention) or
    # broker-side, instead of leaving both as standing guesses. A real
    # storm can be 150+ failed attempts -- logging a full resource
    # snapshot on every one would just be noise, so it's captured once at
    # the start of an outage and once at recovery, not on every retry in
    # between.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    client.disconnect()
    fake._fail_init = True

    with patch("bot.orchestrator.resource_snapshot", return_value="load=7.2,4.1,3.8 mem=1.8/2.0GB") as mock_snap, \
         caplog.at_level("INFO", logger="bot.orchestrator"):
        bot._try_reconnect()  # attempt 1 -- first failure of this outage
        bot._next_reconnect_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        bot._try_reconnect()  # attempt 2 -- same outage, no new snapshot
        bot._next_reconnect_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        bot._try_reconnect()  # attempt 3 -- still no new snapshot

        assert mock_snap.call_count == 1
        assert "load=7.2,4.1,3.8" in caplog.text

        fake._fail_init = False
        bot._next_reconnect_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        bot._try_reconnect()  # recovers -- one more snapshot, at recovery

    assert mock_snap.call_count == 2
    assert "resources at recovery" in caplog.text


# ---- rich event descriptions for the Telegram feed ----

def test_a_placed_entry_logs_the_strategys_full_reasoning(tmp_path, caplog):
    # Direct request: "everything ... thought process, structure
    # alignment, confirmation, entry" -- not just "allow"/"placed". The
    # bias/alignment/trigger/key-level/stop/target context already
    # exists on every TradeRecord; this is what actually surfaces it
    # outside the audit database.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]), \
         caplog.at_level("INFO", logger="bot.orchestrator"):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    text = caplog.text
    assert "EURUSD: entry_attempt (allow) -- placed" in text
    assert "confirmation: engulfing" in text
    assert "aligned: Weekly,Daily,H4" in text
    assert "bias by timeframe: Weekly=bullish" in text
    assert "stop 1.1729" in text and "target 1.17626" in text
    assert "risking $" in text


def test_entry_attempt_logs_the_signals_own_candle_time(tmp_path, caplog):
    # Direct question raised 2026-08-29: is a logged entry_attempt for a
    # fresh signal, or a stale one caught up late after an outage (the
    # watermark-widening and storyline-gap-replay fixes both legitimately
    # act on an older candle than the one that just closed)? Before this,
    # nothing distinguished the two -- not the audit db (no entry_time
    # column existed) and not Telegram (only the log line's OWN
    # timestamp, i.e. when it was written, was visible).
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    signal_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(signal_time)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]), \
         caplog.at_level("INFO", logger="bot.orchestrator"):
        mock_new_candle.return_value = type("C", (), {"time": signal_time})()
        bot.run_once()

    assert f"signal candle: {signal_time}" in caplog.text
    assert audit.recent(1)[0]["entry_time"] == str(signal_time)


def test_a_declined_entry_still_logs_the_full_reasoning(tmp_path, caplog):
    # A decline is a separate axis from what the strategy saw -- the
    # setup's own reasoning must show even when the risk manager says no,
    # otherwise a stream of declines with no context ("why does it keep
    # saying no?") is exactly the kind of thing this exists to answer.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    bot.risk_manager.accepting_entries = False
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]), \
         caplog.at_level("INFO", logger="bot.orchestrator"):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    assert "confirmation: engulfing" in caplog.text
    assert "decline_phase_not_accepting" in caplog.text


def test_a_closed_trade_logs_entry_and_exit_price_together(tmp_path, caplog):
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    row_id = audit.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok",
                                          instrument="EURUSD", trade_id="1"))
    bot.tracked_positions[("EURUSD", 55)] = TrackedPosition(
        row_id=row_id, instrument="EURUSD", ticket=55, risk_amount=1000.0, entry_price=1.17374)
    fake.deals_by_position[55] = (
        make_deal(entry=fake.DEAL_ENTRY_OUT, price=1.17290, profit=-1000.0, reason=fake.DEAL_REASON_SL),
    )

    with caplog.at_level("INFO", logger="bot.orchestrator"):
        bot._record_closed_trade(bot.tracked_positions.pop(("EURUSD", 55)), bot._account_state())

    assert "stop_hit" in caplog.text
    assert "entry 1.17374 -> exit 1.1729" in caplog.text
    assert "-1.00R" in caplog.text and "$-1000.00" in caplog.text


def test_run_once_still_polls_health_every_cycle_even_while_backing_off(tmp_path):
    # The backoff lives entirely inside _try_reconnect() -- run_once()'s
    # own per-poll health check is untouched, so a reconnect that
    # succeeds between polls (e.g. because the underlying terminal came
    # back on its own) is still noticed on the very next run_once() call
    # rather than only once the backoff window happens to elapse.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    client.disconnect()
    fake._fail_init = True
    fake.initialize_calls = 0

    bot.run_once()
    assert fake.initialize_calls == 1

    bot.run_once()  # still inside the backoff window
    assert fake.initialize_calls == 1  # no wasted attempt

    fake._fail_init = False
    bot._next_reconnect_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    bot.run_once()
    assert fake.initialize_calls == 2
    assert client.is_healthy()


def test_run_once_skips_iteration_when_account_state_fetch_fails(tmp_path):
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    fake.account = None  # account_info() will return None -> MT5ConnectionError

    bot.run_once()
    assert audit.recent(10) == []


def test_check_instrument_always_asks_run_backtest_for_both_live_safety_filters(tmp_path):
    # avoid_rollover_entries: confirmed live 2026-08-31, a GBPAUD entry at
    # 22:00 UTC filled 54 points worse than requested, turning $1,000 of
    # intended risk into a $1,530.32 realized loss -- STRATEGY.md Section
    # 8's documented session-rollover risk, which the live bot had never
    # actually implemented. A 2026-09-01 A/B backtest showed this
    # window's signals are fine on paper, but that comparison has no
    # slippage model and so cannot see the execution risk this flag
    # exists to avoid -- direct instruction was to enable it live
    # regardless of the backtest R cost.
    #
    # min_reward_r=1.0: direct 2026-09-01 question, "a trade of less than
    # 1R doesn't make sense to hold." Unlike the rollover flag, this one
    # is a clean backtest-confirmed improvement, not a tradeoff: the
    # removed trades were net losers (-16.1R, 44.6% win rate vs. 51.7%
    # overall) -- skipping them raised total R, win rate, AND avg R/trade.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed",
                       return_value=type("C", (), {"time": entry_time})()), \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[]) as mock_rb:
        bot.run_once()

    mock_rb.assert_called_once()
    assert mock_rb.call_args.kwargs.get("avoid_rollover_entries") is True
    assert mock_rb.call_args.kwargs.get("min_reward_r") == 1.0


# ---- health-based circuit breaker ----

def test_run_once_logs_a_health_halt_and_skips_instrument_checks(tmp_path):
    fake = FakeMT5()
    fake.account.balance = 88000.0
    fake.account.equity = 88000.0  # -12%, past the 10% overall limit
    bot, audit, client = make_bot(fake, tmp_path)

    with patch("bot.orchestrator.run_backtest") as mock_rb:
        bot.run_once()

    mock_rb.assert_not_called()
    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "health_halt"
    assert bot.halted is True


def test_run_once_clears_halted_flag_once_equity_recovers(tmp_path):
    fake = FakeMT5()
    fake.account.balance = 88000.0
    fake.account.equity = 88000.0
    bot, audit, client = make_bot(fake, tmp_path)
    with patch("bot.orchestrator.run_backtest"):
        bot.run_once()
    assert bot.halted is True

    fake.account.balance = 100000.0
    fake.account.equity = 100000.0
    with patch("bot.orchestrator.run_backtest") as mock_rb, \
         patch("bot.orchestrator.sync_recent_from_mt5"):
        mock_rb.return_value = []
        bot.run_once()
    assert bot.halted is False


# ---- new-candle-triggered signal detection ----

def test_no_new_candle_means_no_run_backtest_call(tmp_path):
    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = []
    bot, audit, client = make_bot(fake, tmp_path)
    with patch("bot.orchestrator.run_backtest") as mock_rb:
        bot.run_once()
    mock_rb.assert_not_called()


# ---- the storyline gate: skip the expensive search on pairs that aren't set up ----

def test_a_waiting_instrument_never_reaches_run_backtest(tmp_path):
    # The whole point of the gate: on a pair whose Daily and H4 haven't
    # aligned, the H1 entry search (tens of seconds of full-history work)
    # must not run at all. Running it on all 25 instruments every hour is
    # what put the live bots hours behind -- see OPERATIONS_LOG.md.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), \
         patch.object(LiveBot, "_storyline_says_hunt", return_value=False), \
         patch("bot.orchestrator.run_backtest") as mock_rb:
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    mock_rb.assert_not_called()
    assert audit.recent(10) == []


def test_the_gate_rebuilds_its_context_only_when_a_higher_timeframe_closes(tmp_path):
    # The Weekly/Daily/H4 context is what makes the gate cheap: it must
    # be reused across H1 closes, not rebuilt on each one.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    candle = type("C", (), {"time": entry_time})()

    def only_h1_closes(instrument, timeframe):
        return candle if timeframe == "H1" else None

    fake_ctx = object()
    with patch.object(bot.mt5_client, "new_candle_closed", side_effect=only_h1_closes), \
         patch("bot.orchestrator.build_htf_context", return_value=fake_ctx) as mock_build, \
         patch("bot.orchestrator.storyline_at") as mock_story:
        mock_story.return_value = type("S", (), {
            "stage": "waiting_htf", "reason": "x",
            "weekly_confirmed_at": None, "daily_confirmed_at": None, "h4_confirmed_at": None,
        })()
        bot._storyline_says_hunt("EURUSD", entry_time)   # first time -- must build
        bot._storyline_says_hunt("EURUSD", entry_time)   # no HTF close since -- must reuse

    assert mock_build.call_count == 1


def test_storyline_transition_is_logged_with_each_timeframes_own_confirmation_time(tmp_path, caplog):
    # Confirmed live: the "hunting"/"waiting" log line used to say e.g.
    # "Weekly/Daily/H4 aligned bullish" with no way to tell whether each
    # of those actually just happened or was sitting near the edge of
    # ALIGNMENT_LOOKBACK. Direct 2026-08-30 request: show each
    # timeframe's own confirmation date/time so that's verifiable from
    # the Telegram log alone.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    candle = type("C", (), {"time": entry_time})()

    weekly_time = pd.Timestamp("2026-01-05T00:00:00+00:00")
    daily_time = pd.Timestamp("2026-01-12T00:00:00+00:00")
    h4_time = pd.Timestamp("2026-01-13T12:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed", return_value=candle), \
         patch("bot.orchestrator.build_htf_context", return_value=object()), \
         patch("bot.orchestrator.storyline_at") as mock_story, \
         caplog.at_level("INFO", logger="bot.orchestrator"):
        mock_story.return_value = type("S", (), {
            "stage": "hunting", "reason": "Weekly/Daily/H4 aligned bullish -- watching H1 for the entry",
            "weekly_confirmed_at": weekly_time, "daily_confirmed_at": daily_time,
            "h4_confirmed_at": h4_time,
        })()
        bot._storyline_says_hunt("EURUSD", entry_time)

    [record] = [r for r in caplog.records if "aligned bullish" in r.getMessage()]
    message = record.getMessage()
    assert f"Weekly@{weekly_time}" in message
    assert f"Daily@{daily_time}" in message
    assert f"H4@{h4_time}" in message


def test_a_sustained_new_candle_closed_failure_is_logged_once_not_every_poll(tmp_path, caplog):
    # Confirmed live 2026-08-30: a weekend market closure made
    # new_candle_closed(H1) fail on EVERY 5-second poll, for every
    # instrument, with no dedup at all -- ~2,800 Telegram messages in 3
    # hours. The failure is real and must still be logged (it's
    # WARNING-level for a reason), just once per OUTAGE, not once per
    # poll -- even though the exact error text drifts over time (see the
    # next test): a still-ongoing failure is not a new outage.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         caplog.at_level("WARNING", logger="bot.orchestrator"):
        state = object()
        mock_new_candle.side_effect = MT5ConnectionError("offset -39h")
        bot._check_instrument("EURUSD", state)
        bot._check_instrument("EURUSD", state)
        # The offset-detection error text drifts roughly hourly (it's
        # derived from real time) -- a changed message during an
        # UNINTERRUPTED failure must still not re-trigger the alert.
        # Confirmed live 2026-08-30: an earlier version of this fix
        # deduped on message equality instead of failure state, and the
        # ~25 tracked instruments' stale candles cluster close enough
        # together that they all crossed that hourly drift boundary
        # within the same ~15-second window -- still a 25-message burst,
        # still reported as "still spamming."
        mock_new_candle.side_effect = MT5ConnectionError("offset -40h")
        bot._check_instrument("EURUSD", state)

    warnings = [r for r in caplog.records if "new_candle_closed(EURUSD) failed" in r.getMessage()]
    assert len(warnings) == 1


def test_a_new_candle_closed_failure_is_logged_again_after_a_real_recovery(tmp_path, caplog):
    # A silenced failure must not stay silenced forever -- once it
    # recovers (e.g. the market reopens) and then fails again later
    # (a genuinely new outage), that's worth a fresh alert.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         gate_open(), patch("bot.orchestrator.run_backtest", return_value=[]), \
         caplog.at_level("WARNING", logger="bot.orchestrator"):
        state = object()
        mock_new_candle.side_effect = MT5ConnectionError("offset -39h")
        bot._check_instrument("EURUSD", state)  # first failure -- logs
        mock_new_candle.side_effect = None
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot._check_instrument("EURUSD", state)  # recovers -- clears the failure state
        mock_new_candle.side_effect = MT5ConnectionError("offset -40h")
        mock_new_candle.return_value = None
        bot._check_instrument("EURUSD", state)  # a new outage -- logs again

    warnings = [r for r in caplog.records if "new_candle_closed(EURUSD) failed" in r.getMessage()]
    assert len(warnings) == 2


# ---- resilience: one instrument's unexpected error shouldn't kill the loop ----

def test_unexpected_error_on_one_instrument_does_not_stop_the_others(tmp_path):
    # Confirmed live: an uncaught exception inside _check_instrument() for
    # ONE instrument (e.g. a cache read/write edge case, not an
    # MT5ConnectionError -- those are already handled) used to propagate
    # out of run_once() and kill the whole process, taking every other
    # tracked instrument down with it.
    fake = FakeMT5()
    fake.symbols.setdefault("GBPUSD", make_symbol_info(point=0.0001))
    bot, audit, client = make_bot(fake, tmp_path, instruments=("EURUSD", "GBPUSD"))

    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)
    record.instrument = "GBPUSD"

    def new_candle_side_effect(instrument, timeframe):
        if instrument == "EURUSD":
            raise RuntimeError("simulated unexpected failure")
        return type("C", (), {"time": entry_time})()

    with patch.object(bot.mt5_client, "new_candle_closed", side_effect=new_candle_side_effect), \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        bot.run_once()  # must not raise

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["instrument"] == "GBPUSD"  # the healthy instrument was still checked


def test_fresh_signal_declined_by_risk_manager_is_logged_and_not_placed(tmp_path):
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    bot.risk_manager.accepting_entries = False  # force a decline

    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "entry_attempt"
    assert rows[0]["decision"] == "decline_phase_not_accepting"
    assert fake.order_send_calls == []


def test_fresh_signal_allowed_and_placed_successfully_is_tracked(tmp_path):
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["decision"] == "allow"
    assert rows[0]["trigger_type"] == "engulfing"
    assert len(fake.order_send_calls) == 1
    assert len(bot.tracked_positions) == 1


def test_fresh_signal_with_invalid_sizing_is_declined_before_any_order(tmp_path):
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001, volume_min=1000.0, volume_step=1000.0)  # absurdly high minimum
    bot, audit, client = make_bot(fake, tmp_path)

    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert rows[0]["decision"].startswith("decline_sizing_")
    assert fake.order_send_calls == []
    assert bot.tracked_positions == {}


def test_cold_start_only_matches_the_exact_candle_that_just_closed(tmp_path):
    # The FIRST check for an instrument in this process's lifetime has no
    # watermark yet (_last_entry_time is empty). run_backtest() returns
    # its full deterministic history on every call, so matching anything
    # other than the exact new candle here would replay every historical
    # trade back to whenever the cache begins -- a real trade from three
    # days ago is correctly NOT re-entered just because it's still in
    # that list. See the catch-up test below for the case this does NOT
    # cover: a signal missed between two checks of the SAME process.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    new_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    old_time = pd.Timestamp("2026-01-10T09:00:00+00:00")
    records = [a_trade_record(old_time, trade_id=1), a_trade_record(new_time, trade_id=2)]

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=records):
        mock_new_candle.return_value = type("C", (), {"time": new_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["trade_id"] == "2"


def test_a_signal_missed_between_two_checks_of_the_same_process_is_still_caught(tmp_path):
    # The real bug, confirmed live 2026-08-27/28: mt5_client.new_candle_
    # closed() reports only the single most-recently-seen bar (see its
    # own docstring), never a queue of every bar that closed while this
    # instrument wasn't checked. During an MT5 reconnect storm, run_once()
    # returns before _check_instrument() is ever called for anything --
    # so if TWO H1 candles close in that stretch, the OLD exact-match
    # logic would see only the newer one on the next successful poll and
    # silently, permanently lose the earlier signal: no exception, no log
    # line, no audit row. 6 real signals across both live bots vanished
    # exactly this way in one 36-hour window.
    #
    # First check establishes the watermark at T1 (a quiet candle, no
    # signal). Then TWO more H1 candles close before the bot manages
    # another successful check -- new_candle_closed() can only ever
    # report the LATEST one, T3 -- but run_backtest() (deterministic,
    # full history) shows a real trade sitting on the skipped T2. Both
    # T2's trade and any genuine T3 trade must be considered, not just
    # whichever one happens to be "the new candle" this cycle.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    t1 = pd.Timestamp("2026-01-13T12:00:00+00:00")
    t2 = pd.Timestamp("2026-01-13T13:00:00+00:00")  # closed during the outage -- no poll saw it directly
    t3 = pd.Timestamp("2026-01-13T14:00:00+00:00")  # the first candle a poll actually observes again

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[]):
        mock_new_candle.return_value = type("C", (), {"time": t1})()
        bot.run_once()  # establishes the watermark at t1; no signal, no audit row

    assert audit.recent(10) == []

    # The outage: two candles (t2, t3) close, but new_candle_closed() can
    # only ever report the newest -- exactly what the real MT5 client
    # does when polling resumes after a gap.
    missed_during_outage = a_trade_record(t2, trade_id=1)
    just_closed = a_trade_record(t3, trade_id=2, direction=Direction.BEARISH)
    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[missed_during_outage, just_closed]):
        mock_new_candle.return_value = type("C", (), {"time": t3})()
        bot.run_once()

    rows = audit.recent(10)
    assert {r["trade_id"] for r in rows} == {"1", "2"}  # BOTH -- the skipped one and the current one


def test_a_signal_from_before_the_watermark_is_not_reconsidered(tmp_path):
    # Symmetric to the catch-up test: once t2 has been evaluated (whether
    # or not it produced a trade), a LATER poll must not re-examine
    # anything at or before it -- run_backtest()'s history is
    # deterministic, so without this a resolved trade would be reported
    # again on every subsequent candle close.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    t1 = pd.Timestamp("2026-01-13T12:00:00+00:00")
    t2 = pd.Timestamp("2026-01-13T13:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[a_trade_record(t1, trade_id=1)]):
        mock_new_candle.return_value = type("C", (), {"time": t1})()
        bot.run_once()
    assert len(audit.recent(10)) == 1

    # t2 closes with no NEW trade of its own, but the old t1 trade is
    # still sitting in run_backtest()'s full (deterministic) result set.
    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[a_trade_record(t1, trade_id=1)]):
        mock_new_candle.return_value = type("C", (), {"time": t2})()
        bot.run_once()

    assert len(audit.recent(10)) == 1  # still just the one row -- t1 was not re-logged


def test_a_caught_up_signal_past_the_staleness_cutoff_is_declined_not_traded(tmp_path):
    # Confirmed live 2026-08-29: EURJPY's 16:00/17:00 UTC candles from the
    # PREVIOUS day were still attempted as live market orders 14-15 hours
    # later. The watermark-widening catch-up (2026-08-28) exists so a
    # missed signal is never silently dropped -- but trading it that
    # stale, against a materially different current price, is a separate
    # and much worse problem than just reporting it. Direct request:
    # "leave the trade if it have passed" -- still logged with full
    # reasoning (declined, not silently dropped), just never reaches
    # _consider_entry/the risk manager/MT5.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    # Watermark established BEFORE the stale signal's own candle, then
    # recovery lands 16h after it -- inside the watermark-widening catch-up
    # window, but well past the 3-hour staleness cutoff.
    watermark_time = pd.Timestamp("2026-01-12T20:00:00+00:00")
    stale_signal = pd.Timestamp("2026-01-12T22:00:00+00:00")
    recovery_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[]):
        mock_new_candle.return_value = type("C", (), {"time": watermark_time})()
        bot.run_once()  # establishes the watermark; no signal
    assert audit.recent(10) == []

    stale_record = a_trade_record(stale_signal, trade_id=1)
    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[stale_record]):
        mock_new_candle.return_value = type("C", (), {"time": recovery_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["decision"] == "decline_stale_signal"
    assert fake.order_send_calls == []  # never reached execution


def test_a_caught_up_signal_still_within_the_cutoff_is_traded_normally(tmp_path):
    # Symmetric to the staleness-decline test: a signal caught up quickly
    # (well within the cutoff) must be traded exactly as before -- the
    # cutoff isn't a general brake on the watermark-widening catch-up,
    # only on genuinely stale ones.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    watermark_time = pd.Timestamp("2026-01-13T12:00:00+00:00")
    recent_signal = pd.Timestamp("2026-01-13T13:00:00+00:00")   # 1h old -- well inside the cutoff
    recovery_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[]):
        mock_new_candle.return_value = type("C", (), {"time": watermark_time})()
        bot.run_once()

    record = a_trade_record(recent_signal, trade_id=1)
    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        mock_new_candle.return_value = type("C", (), {"time": recovery_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["decision"] == "allow"


def test_a_signal_whose_gate_closed_before_the_recovery_poll_is_still_caught(tmp_path):
    # Confirmed live 2026-08-29: NZDUSD's 13:00 UTC candle passed the
    # storyline gate (Daily/H4 aligned) at the time. A reconnect storm
    # spanned that exact hour; by the time polling recovered, the bias
    # had moved on and the gate said WAITING at the recovery candle. The
    # OLD code checked the gate only there, saw WAITING, and returned
    # before run_backtest() was ever called -- so unlike the entry-
    # matching bug the watermark-widening fix already covers, there was
    # no watermark to widen: the signal was never even searched for.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    t1 = pd.Timestamp("2026-01-13T12:00:00+00:00")  # establishes the watermark
    t2 = pd.Timestamp("2026-01-13T13:00:00+00:00")  # gate said HUNT here (the storm's window)
    t3 = pd.Timestamp("2026-01-13T14:00:00+00:00")  # recovery poll -- gate now says WAITING

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[]):
        mock_new_candle.return_value = type("C", (), {"time": t1})()
        bot.run_once()  # establishes the watermark at t1; no signal
    assert audit.recent(10) == []

    missed_during_the_gap = a_trade_record(t2, trade_id=1)
    gate_by_time = {t2: True, t3: False}
    h1_candles = [type("C", (), {"time": t})() for t in (t1, t2, t3)]

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), \
         patch.object(LiveBot, "_storyline_says_hunt", side_effect=lambda instrument, t: gate_by_time[t]), \
         patch("bot.orchestrator.load_candles", return_value=h1_candles), \
         patch("bot.orchestrator.run_backtest", return_value=[missed_during_the_gap]):
        mock_new_candle.return_value = type("C", (), {"time": t3})()
        bot.run_once()

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["trade_id"] == "1"


def test_the_gap_replay_is_skipped_entirely_on_the_common_no_gap_path(tmp_path):
    # Steady-state polling (gate says HUNT right at the new candle) must
    # never even look at load_candles() -- the whole point of checking
    # new_candle_time first is that this stays exactly as cheap as before
    # the gap-replay fix existed.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.load_candles") as mock_load, \
         patch("bot.orchestrator.run_backtest", return_value=[]):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    mock_load.assert_not_called()


# ---- reconciliation ----

def test_reconcile_closed_positions_records_outcome_and_untracks(tmp_path):
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    row_id = audit.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok",
                                          instrument="EURUSD", trade_id="1"))
    bot.tracked_positions[("EURUSD", 55)] = TrackedPosition(
        row_id=row_id, instrument="EURUSD", ticket=55, risk_amount=1000.0, entry_price=1.17374)

    fake.deals_by_position[55] = (
        make_deal(entry=fake.DEAL_ENTRY_OUT, price=1.17290, profit=-1000.0, reason=fake.DEAL_REASON_SL),
    )
    fake.positions = []  # no longer open -> should be reconciled

    with patch("bot.orchestrator.run_backtest", return_value=[]):
        bot.run_once()

    assert ("EURUSD", 55) not in bot.tracked_positions
    rows = audit.recent(10)
    closed_row = next(r for r in rows if r["trade_id"] == "1")
    assert closed_row["exit_reason"] == "stop_hit"
    assert closed_row["r_multiple"] == -1.0
    assert closed_row["realized_pnl"] == -1000.0


def test_reconcile_sets_accepting_entries_false_when_target_is_hit(tmp_path):
    fake = FakeMT5()
    fake.account.balance = 108500.0  # past the 8% phase1 target
    fake.account.equity = 108500.0
    bot, audit, client = make_bot(fake, tmp_path)

    row_id = audit.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok",
                                          instrument="EURUSD", trade_id="1"))
    bot.tracked_positions[("EURUSD", 56)] = TrackedPosition(
        row_id=row_id, instrument="EURUSD", ticket=56, risk_amount=1000.0, entry_price=1.17374)
    fake.deals_by_position[56] = (
        make_deal(entry=fake.DEAL_ENTRY_OUT, price=1.17626, profit=3000.0, reason=fake.DEAL_REASON_TP),
    )
    fake.positions = []

    with patch("bot.orchestrator.run_backtest", return_value=[]):
        bot.run_once()

    assert bot.risk_manager.accepting_entries is False
    rows = audit.recent(10)
    assert any(r["event_type"] == "phase_transition" for r in rows)
