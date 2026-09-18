from contextlib import contextmanager
from types import SimpleNamespace
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


# A fixed "now" for every test in this file.
#
# Until 2026-09-18 these tests read the real wall clock, because
# `_weekend_is_close()` and `_too_late_to_open()` default `now` to
# `datetime.now(timezone.utc)`. That made 31 of them fail every Friday
# evening and all weekend, on a completely clean tree, for reasons
# having nothing to do with the code under test -- CI red on Fridays,
# and a real regression indistinguishable from the calendar. Found while
# reviewing something else: a fix was "breaking" 31 tests that were
# already broken before it was written.
#
# This was already known: test_resting_order_survives_while_the_setup_is_
# merely_waiting's docstring records it being hit on 2026-09-11, and three
# tests were given `patch.object(LiveBot, "_weekend_is_close", ...)` as a
# local workaround. The other 31 were left calendar-flaky, so the problem
# came straight back the next Friday. Fixing it once, here, is what stops
# that recurring.
#
# Wednesday noon UTC: mid-week, nowhere near the Friday flatten window,
# so the weekend guards are simply inactive unless a test asks for them.
# The tests that genuinely exercise weekend logic are unaffected -- they
# pass `now=` explicitly (test_weekend_window_tracks_the_new_york_close_
# through_dst and friends) or patch `_weekend_is_close` outright.
FROZEN_NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze_clock():
    real_now = datetime.now

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_NOW if tz else FROZEN_NOW.replace(tzinfo=None)

    with patch("bot.orchestrator.datetime", _FixedDatetime):
        yield


def _bar(high, low, time="2026-09-01T18:00Z"):
    """Minimal candle stand-in -- check_setup() reads high/low/time."""
    from types import SimpleNamespace
    return SimpleNamespace(high=high, low=low, time=time)

RULES = PhaseRules(daily_dd_limit_pct=0.04, overall_dd_limit_pct=0.10,
                    risk_normal=1000.0, risk_reduced=500.0, de_risk_at_pct=0.05,
                    profit_target_pct=0.08)
CREDS = MT5Credentials(login=1, password="pw", server="Demo")


def make_profile():
    return AccountProfile(account_type="prop_firm", active_phase="phase1",
                           phases={"phase1": PhaseConfig(rules=RULES, credentials=CREDS)})


def make_bot(fake, tmp_path, instruments=("EURUSD",), **extra):
    fake.symbols.setdefault("EURUSD", make_symbol_info(point=0.0001))
    client = MT5Client(fake, login=1, password="pw", server="Demo", server_utc_offset=pd.Timedelta(0))
    client.connect()
    execu = MT5Execution(fake)
    audit = AuditLog(str(tmp_path / "audit.db"))
    return LiveBot(profile=make_profile(), mt5_client=client, mt5_exec=execu,
                    audit_log=audit, instruments=instruments, **extra), audit, client


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
        delays.append((bot._next_reconnect_at - FROZEN_NOW).total_seconds())
        bot._next_reconnect_at = FROZEN_NOW - timedelta(seconds=1)

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

    bot._next_reconnect_at = FROZEN_NOW - timedelta(seconds=1)
    fake._fail_init = False  # the terminal recovers
    bot._try_reconnect()

    assert bot._reconnect_attempts == 0
    assert bot._next_reconnect_at is None

    # A LATER failure must start the backoff over from the base delay,
    # not continue from wherever the previous outage left off.
    client.disconnect()
    fake._fail_init = True
    bot._try_reconnect()
    delay = (bot._next_reconnect_at - FROZEN_NOW).total_seconds()
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
        bot._next_reconnect_at = FROZEN_NOW - timedelta(seconds=1)
        bot._try_reconnect()  # attempt 2 -- same outage, no new snapshot
        bot._next_reconnect_at = FROZEN_NOW - timedelta(seconds=1)
        bot._try_reconnect()  # attempt 3 -- still no new snapshot

        assert mock_snap.call_count == 1
        assert "load=7.2,4.1,3.8" in caplog.text

        fake._fail_init = False
        bot._next_reconnect_at = FROZEN_NOW - timedelta(seconds=1)
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
    bot._next_reconnect_at = FROZEN_NOW - timedelta(seconds=1)
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


def test_check_instrument_passes_default_origin_and_history_settings(tmp_path):
    """Defaults must reach run_backtest() unchanged -- matches every
    behavior before 2026-09-13."""
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed",
                       return_value=type("C", (), {"time": entry_time})()), \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[]) as mock_rb:
        bot.run_once()

    assert mock_rb.call_args.kwargs.get("origin_kind") == "sweep_break"
    assert mock_rb.call_args.kwargs.get("close_based_sweep_break") is False
    assert mock_rb.call_args.kwargs.get("max_history_years") is None


def test_check_instrument_passes_configured_origin_and_history_settings(tmp_path):
    """A configured origin_kind/close_based_sweep_break/history_window_years
    must actually reach run_backtest() -- and the per-instrument window
    lookup must be keyed by the instrument being checked, not passed
    wholesale (an instrument missing from the dict gets None, i.e.
    uncapped, not a KeyError)."""
    fake = FakeMT5()
    bot, audit, client = make_bot(
        fake, tmp_path, origin_kind="any", close_based_sweep_break=True,
        history_window_years={"EURUSD": {"D": 8, "W": 8, "H4": 4, "H1": 4},
                               "GBPJPY": {"D": 10, "W": 10, "H4": 5, "H1": 5}},
    )
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed",
                       return_value=type("C", (), {"time": entry_time})()), \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[]) as mock_rb:
        bot.run_once()

    assert mock_rb.call_args.kwargs.get("origin_kind") == "any"
    assert mock_rb.call_args.kwargs.get("close_based_sweep_break") is True
    assert mock_rb.call_args.kwargs.get("max_history_years") == {"D": 8, "W": 8, "H4": 4, "H1": 4}


# ---- health-based circuit breaker ----

def test_run_once_logs_a_health_halt(tmp_path):
    fake = FakeMT5()
    fake.account.balance = 88000.0
    fake.account.equity = 88000.0  # -12%, past the 10% overall limit
    bot, audit, client = make_bot(fake, tmp_path)

    bot.run_once()

    rows = audit.recent(10)
    assert any(r["event_type"] == "health_halt" for r in rows)
    assert bot.halted is True
    assert bot.halt_reason


def test_a_halt_still_reports_the_setup_it_could_not_take(tmp_path, caplog):
    """A halt must stop the ORDER, not the ANALYSIS.

    run_once() used to `return` at the health gate, skipping every
    instrument -- so a halt made the bot silent for the rest of the day.
    On 2026-09-15 that silence followed a drawdown breach that never
    happened, and the only way to find out a whole day had been skipped
    was to go digging in the audit database.

    Operator: "once it has seen a setup you should always send the setup
    to my Telegram, even if it cannot take the setup because of the
    account limits... I want to be seeing the thought process."
    """
    fake = FakeMT5()
    fake.account.balance = 88000.0
    fake.account.equity = 88000.0  # past the overall limit -> halted
    bot, audit, client = make_bot(fake, tmp_path)
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]), \
         caplog.at_level("INFO", logger="bot.orchestrator"):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    attempts = [r for r in audit.recent(20) if r["event_type"] == "entry_attempt"]
    assert len(attempts) == 1, "the setup must still be recorded while halted"
    assert attempts[0]["decision"] == "decline_account_halted"

    text = caplog.text
    assert "SETUP FOUND but the account is halted" in text
    # ...and it carries the full read, exactly as an allowed entry would,
    # so the message is worth receiving rather than a bare refusal.
    assert "confirmation: engulfing" in text
    assert "stop 1.1729" in text and "target 1.17626" in text

    # The one thing that must NOT happen.
    assert fake.order_send_calls == []


def test_the_halt_clearing_is_announced(tmp_path, caplog):
    """The recovery used to be silent -- the flag flipped back with no
    log line, so from outside there was no way to tell a halt had ended
    other than trades resuming."""
    fake = FakeMT5()
    fake.account.balance = 88000.0
    fake.account.equity = 88000.0
    bot, audit, client = make_bot(fake, tmp_path)
    bot.run_once()
    assert bot.halted is True

    fake.account.balance = 100000.0
    fake.account.equity = 100000.0
    with caplog.at_level("INFO", logger="bot.orchestrator"):
        bot.run_once()

    assert bot.halted is False
    assert bot.halt_reason == ""
    assert any(r["event_type"] == "health_clear" for r in audit.recent(20))
    assert "halt cleared" in caplog.text


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


def test_a_caught_up_signal_past_the_staleness_cutoff_rests_a_limit_not_a_market_order(tmp_path):
    # Confirmed live 2026-08-29: EURJPY's 16:00/17:00 UTC candles from the
    # PREVIOUS day were still attempted as live MARKET orders 14-15 hours
    # later, against a materially different current price than the stop/
    # target were sized for. 2026-09-15 REVISED: a market fill this late
    # is never safe (check_setup() can't see current-price drift, and
    # compute_lot_size()'s drift guard allows up to 100% of the stop
    # distance -- nowhere near tight enough), so a signal in this window
    # (past STALE_ENTRY_CUTOFF but within STALE_ENTRY_CUTOFF_LIMIT) now
    # rests a LIMIT at its own entry price instead of firing at market --
    # same mechanism the limit-order bot already uses, which only ever
    # fills at the intended price or not at all. Here the H1 cache can't
    # be read (unmocked), so _place_limit_entry() itself fails closed
    # (decline_setup_unverifiable) rather than resting against an
    # unverified thesis -- still never reaching a market order.
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    # Watermark established BEFORE the stale signal's own candle, then
    # recovery lands 16h after it -- inside the watermark-widening catch-up
    # window, past the 3-hour market cutoff but within the 24h backstop.
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
    assert rows[0]["decision"] == "decline_setup_unverifiable"
    assert fake.order_send_calls == []  # never reached market execution


def test_a_signal_past_the_limit_backstop_too_is_declined_outright(tmp_path):
    """Beyond STALE_ENTRY_CUTOFF_LIMIT (24h), even the limit-rescue isn't
    attempted -- same hard backstop the limit-order bot itself uses."""
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    watermark_time = pd.Timestamp("2026-01-12T08:00:00+00:00")
    ancient_signal = pd.Timestamp("2026-01-12T10:00:00+00:00")
    recovery_time = pd.Timestamp("2026-01-13T14:00:00+00:00")  # 28h later

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[]):
        mock_new_candle.return_value = type("C", (), {"time": watermark_time})()
        bot.run_once()

    ancient_record = a_trade_record(ancient_signal, trade_id=1)
    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[ancient_record]):
        mock_new_candle.return_value = type("C", (), {"time": recovery_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["decision"] == "decline_stale_signal"
    assert "too old to act on at all" in rows[0]["reason"]
    assert fake.order_send_calls == []


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


def test_a_stale_market_signal_still_alive_by_price_rests_a_limit(tmp_path):
    """2026-09-15 fix (revised): age alone must never be the verdict for
    a market order -- but a market FILL this late isn't safe either
    (current price may have drifted from entry_price with the stop/
    target still sized for the original level). A signal well past
    STALE_ENTRY_CUTOFF, with price still sitting between entry and stop
    (never breached, never near target), must rest a LIMIT at its own
    entry price via force_limit -- never an immediate market order."""
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    watermark_time = pd.Timestamp("2026-01-12T20:00:00+00:00")
    stale_signal = pd.Timestamp("2026-01-12T22:00:00+00:00")   # 16h before recovery
    recovery_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[]):
        mock_new_candle.return_value = type("C", (), {"time": watermark_time})()
        bot.run_once()

    # a_trade_record(): bullish, entry 1.17374, stop 1.17290, target
    # 1.17626 -- these candles never dip to the stop nor climb 80% of
    # the way to target, so check_setup() reads ALIVE.
    quiet_candles = [_bar(1.17410, 1.17360, time=stale_signal + timedelta(hours=1)),
                     _bar(1.17420, 1.17370, time=stale_signal + timedelta(hours=2))]
    stale_record = a_trade_record(stale_signal, trade_id=1)
    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[stale_record]), \
         patch.object(LiveBot, "_candles_since", return_value=quiet_candles):
        mock_new_candle.return_value = type("C", (), {"time": recovery_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["decision"] == "allow_pending"  # rested, not filled
    assert fake.order_send_calls == [] or all(
        c.get("action") != fake.TRADE_ACTION_DEAL for c in fake.order_send_calls
    ), "must never be an immediate market fill"


def test_a_stale_market_signal_genuinely_stopped_out_is_still_declined(tmp_path):
    """The other half of the 2026-09-15 fix: age is no longer the
    verdict, but a setup that price has actually invalidated must still
    be declined -- just for the real reason (stop breached, via the same
    check_setup() the limit-order rescue path uses), not a clock guess."""
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    watermark_time = pd.Timestamp("2026-01-12T20:00:00+00:00")
    stale_signal = pd.Timestamp("2026-01-12T22:00:00+00:00")
    recovery_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[]):
        mock_new_candle.return_value = type("C", (), {"time": watermark_time})()
        bot.run_once()

    # bullish, stop 1.17290 -- this candle's low trades straight through it.
    breached = [_bar(1.17380, 1.17250, time=stale_signal + timedelta(hours=1))]
    stale_record = a_trade_record(stale_signal, trade_id=1)
    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[stale_record]), \
         patch.object(LiveBot, "_candles_since", return_value=breached):
        mock_new_candle.return_value = type("C", (), {"time": recovery_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["decision"] == "decline_setup_stop_breached"
    assert "invalidation point" in rows[0]["reason"]  # check_setup()'s own STOP_BREACHED wording
    assert fake.order_send_calls == []


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


def test_a_fresh_process_reconstructs_its_watermark_from_the_audit_log_not_a_cold_start(tmp_path):
    # Confirmed live 2026-08-30/31: _last_entry_time lives only in
    # memory, so every process restart -- exactly when a deploy happens,
    # one of the most common times for this to occur -- reset it to
    # cold-start (exact-match-only). A Dukascopy-reference comparison
    # the same day found 9 of 11 signals with zero trace in either audit
    # database. A brand new LiveBot (simulating a fresh process after a
    # restart) must reconstruct its watermark from what the PREVIOUS
    # process durably logged, not silently fall back to exact-match-only
    # and lose a signal that isn't the literal next candle checked.
    from ..audit_log import DecisionRecord

    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    t1 = pd.Timestamp("2026-01-13T12:00:00+00:00")  # the OLD process's last watermark, durably logged
    t2 = pd.Timestamp("2026-01-13T13:00:00+00:00")  # a real signal in the gap -- NOT the next candle
    t3 = pd.Timestamp("2026-01-13T14:00:00+00:00")  # the new process's first candle checked

    audit.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok",
                                 instrument="EURUSD", entry_time=str(t1)))
    assert bot._last_entry_time.get("EURUSD") is None  # genuinely nothing in memory -- a fresh process

    missed_signal = a_trade_record(t2, trade_id=1)
    with patch.object(bot.mt5_client, "new_candle_closed",
                       return_value=type("C", (), {"time": t3})()), \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[missed_signal]):
        bot.run_once()

    rows = audit.recent(10)
    assert any(r["trade_id"] == "1" and r["event_type"] == "entry_attempt"
               and r["reason"] != "ok" for r in rows), \
        "the t2 signal must have been evaluated (accepted or declined), not silently dropped"


def test_a_restart_does_not_redecline_the_exact_signal_it_already_logged(tmp_path):
    """Confirmed live 2026-09-15: JP225's decline_stale_signal for the
    same signal_time (2026-09-15 02:00:00+00:00) was logged TWICE,
    exactly bracketing that day's two bot restarts (07:38 and 15:49) --
    byte-identical entry_time both times. The watermark-reconstruction
    fix above (2026-08-30/31) is supposed to prevent exactly this: it
    reconstructs the watermark from the MOST RECENT entry_attempt this
    instrument ever logged, precisely so a restart can't re-see a signal
    it has already evaluated. If the reconstructed watermark is set from
    a row whose OWN entry_time is signal_time, and run_backtest() (a
    fresh process replays its whole history from scratch, so it
    legitimately re-derives the same historical signal) hands back that
    SAME signal_time again, it must not be re-logged."""
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    signal_time = pd.Timestamp("2026-01-13T02:00:00+00:00")
    new_candle_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    # The OLD process already declined this exact signal as stale and
    # logged it durably -- this is the row a restart must reconstruct
    # its watermark from.
    audit.append(DecisionRecord(event_type="entry_attempt", decision="decline_stale_signal",
                                 reason="stale", instrument="EURUSD", entry_time=str(signal_time)))
    assert bot._last_entry_time.get("EURUSD") is None  # genuinely nothing in memory -- a fresh process

    same_signal_again = a_trade_record(signal_time, trade_id=99)
    with patch.object(bot.mt5_client, "new_candle_closed",
                       return_value=type("C", (), {"time": new_candle_time})()), \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[same_signal_again]):
        bot.run_once()

    rows = audit.recent(10)
    assert not any(r["trade_id"] == "99" for r in rows), \
        "the already-logged signal must not be re-evaluated (and re-declined) after a restart"


def test_a_genuinely_new_instrument_still_starts_cold(tmp_path):
    # The audit log has never seen this instrument -- there is nothing
    # to reconstruct, so this must still be exact-match-only, same as
    # before the watermark-reconstruction fix existed (matching
    # everything run_backtest() has ever produced on a true blank slate
    # would replay history back to whenever the cache begins).
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    old_signal = a_trade_record(pd.Timestamp("2026-01-13T13:00:00+00:00"), trade_id=1)
    new_candle_time = pd.Timestamp("2026-01-13T14:00:00+00:00")

    with patch.object(bot.mt5_client, "new_candle_closed",
                       return_value=type("C", (), {"time": new_candle_time})()), \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[old_signal]):
        bot.run_once()

    assert audit.recent(10) == []  # old_signal's time != new_candle_time -- correctly not matched


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


# ---- limit-order entries (entry_order_type="limit") ----
# Motivated by the 2026-09-02 audit: the bot is never prompt, so a market
# order sent 40 minutes late buys at a price the stop was never sized for.
# See setup_validity.py and place_limit_order().

def _limit_bot(fake, tmp_path, instruments=("EURUSD",)):
    bot, audit, client = make_bot(fake, tmp_path, instruments)
    bot.entry_order_type = "limit"
    return bot, audit, client


def test_market_remains_the_default():
    """Enabling limits must be a deliberate act -- nothing changes for
    existing callers until they ask."""
    fake = FakeMT5()
    assert LiveBot(profile=make_profile(), mt5_client=MT5Client(fake, login=1, password="pw",
                                                                 server="Demo"),
                    mt5_exec=MT5Execution(fake), audit_log=None,
                    instruments=("EURUSD",)).entry_order_type == "market"


def test_limit_entry_rests_an_order_at_the_computed_entry(tmp_path):
    fake = FakeMT5()
    bot, audit, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))

    with patch.object(LiveBot, "_candles_since", return_value=[]):
        bot._consider_entry("EURUSD", record, bot._account_state())

    req = fake.order_send_calls[-1]
    assert req["action"] == fake.TRADE_ACTION_PENDING
    # Snapped to this symbol's 4-digit tick grid -- an unrounded price is
    # rejected INVALID_STOPS (confirmed live 2026-08-29).
    assert req["price"] == pytest.approx(round(record.entry_price, 4))
    assert len(bot.pending_entries) == 1
    row = audit.recent(1)[0]
    assert row["decision"] == "allow_pending"


def test_limit_entry_declines_a_setup_whose_stop_was_already_breached(tmp_path):
    """Late is fine; invalidated is not. The distinction is price, not
    the clock."""
    fake = FakeMT5()
    bot, audit, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))
    breached = [_bar(high=1.17400, low=1.17200)]  # through the 1.17290 stop

    with patch.object(LiveBot, "_candles_since", return_value=breached):
        bot._consider_entry("EURUSD", record, bot._account_state())

    assert bot.pending_entries == {}
    assert not any(c.get("action") == fake.TRADE_ACTION_PENDING
                   for c in fake.order_send_calls)
    assert audit.recent(1)[0]["decision"] == "decline_setup_stop_breached"


def test_resting_order_is_cancelled_once_the_setup_dies(tmp_path):
    fake = FakeMT5()
    bot, audit, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))
    with patch.object(LiveBot, "_candles_since", return_value=[]):
        bot._consider_entry("EURUSD", record, bot._account_state())
    assert len(bot.pending_entries) == 1

    # Now price runs through the stop while the order rests.
    with patch.object(LiveBot, "_candles_since",
                      return_value=[_bar(high=1.17400, low=1.17200)]):
        bot._reconcile_pending_entries(bot._account_state())

    assert bot.pending_entries == {}
    assert fake.orders == []
    assert audit.recent(1)[0]["decision"] == "cancel_pending"


def test_resting_order_survives_while_the_setup_is_merely_waiting(tmp_path):
    """The case the old code threw away as 'stale': price simply hasn't
    come back to the level yet.

    _weekend_is_close() reads the real wall clock when not given `now=`,
    so this (and the two tests below with the same shape) must pin it --
    otherwise the test is calendar-flaky, failing for real every Friday
    evening through the weekend regardless of what it's actually testing.
    Found 2026-09-11 running this suite for the first time on a Friday.
    """
    fake = FakeMT5()
    bot, _, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))
    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._consider_entry("EURUSD", record, bot._account_state())

    with patch.object(LiveBot, "_candles_since",
                      return_value=[_bar(high=1.17390, low=1.17380)]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._reconcile_pending_entries(bot._account_state())

    assert len(bot.pending_entries) == 1
    assert len(fake.orders) == 1


def test_resting_orders_are_cancelled_at_the_weekend_cutoff(tmp_path):
    """Direct operator requirement: nothing rests over the weekend."""
    fake = FakeMT5()
    bot, audit, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))
    with patch.object(LiveBot, "_candles_since", return_value=[]):
        bot._consider_entry("EURUSD", record, bot._account_state())

    # Close is Fri 17:00 New York = 21:00 UTC in September (EDT); the
    # flatten window opens 60 minutes before that.
    assert bot._weekend_is_close(datetime(2026, 9, 4, 20, 15, tzinfo=timezone.utc))
    with patch.object(LiveBot, "_weekend_is_close", return_value=True), \
         patch.object(LiveBot, "_candles_since", return_value=[]):
        bot._reconcile_pending_entries(bot._account_state())

    assert bot.pending_entries == {}
    assert "weekend" in audit.recent(1)[0]["reason"]


def test_weekend_window_tracks_the_new_york_close_through_dst():
    """The broker closes with the NY exchange -- 21:00 UTC under EDT,
    22:00 under EST. A fixed UTC hour would be an hour wrong for half the
    year, so this pins both sides of the changeover."""
    fake = FakeMT5()
    bot = LiveBot(profile=make_profile(),
                   mt5_client=MT5Client(fake, login=1, password="pw", server="Demo"),
                   mt5_exec=MT5Execution(fake), audit_log=None, instruments=("EURUSD",))

    # Midweek: nowhere near it.
    assert not bot._weekend_is_close(datetime(2026, 9, 2, 23, 0, tzinfo=timezone.utc))
    # Friday in EDT: 19:59 UTC is still 61 minutes out; 20:00 is in.
    assert not bot._weekend_is_close(datetime(2026, 9, 4, 19, 59, tzinfo=timezone.utc))
    assert bot._weekend_is_close(datetime(2026, 9, 4, 20, 15, tzinfo=timezone.utc))
    # Friday in EST (December): the same wall-clock 20:15 UTC is now an
    # hour and 45 minutes out, because the close moved to 22:00 UTC.
    assert not bot._weekend_is_close(datetime(2026, 12, 4, 20, 15, tzinfo=timezone.utc))
    assert bot._weekend_is_close(datetime(2026, 12, 4, 21, 15, tzinfo=timezone.utc))
    # The weekend itself counts -- "minutes to next Friday" alone would
    # read Saturday as the safest moment of the week.
    assert bot._weekend_is_close(datetime(2026, 9, 5, 1, 0, tzinfo=timezone.utc))
    assert bot._weekend_is_close(datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc))
    # Sunday after the 17:00 NY reopen: trading again.
    assert not bot._weekend_is_close(datetime(2026, 9, 6, 22, 0, tzinfo=timezone.utc))


def test_new_entries_stop_well_before_the_close():
    fake = FakeMT5()
    bot = LiveBot(profile=make_profile(),
                   mt5_client=MT5Client(fake, login=1, password="pw", server="Demo"),
                   mt5_exec=MT5Execution(fake), audit_log=None, instruments=("EURUSD",))
    # 4h before a 21:00 UTC close is 17:00 UTC.
    assert not bot._too_late_to_open(datetime(2026, 9, 4, 16, 30, tzinfo=timezone.utc))
    assert bot._too_late_to_open(datetime(2026, 9, 4, 17, 30, tzinfo=timezone.utc))


def test_a_filled_limit_becomes_a_tracked_position(tmp_path):
    fake = FakeMT5()
    bot, _, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))
    with patch.object(LiveBot, "_candles_since", return_value=[]):
        bot._consider_entry("EURUSD", record, bot._account_state())

    # The broker fills it: gone from the order book, present as a position.
    fake.orders = []
    fake.positions = [make_position(ticket=9001, symbol="EURUSD", volume=0.5,
                                     price_open=record.entry_price, sl=record.stop_loss)]

    bot._reconcile_pending_entries(bot._account_state())

    assert bot.pending_entries == {}
    assert ("EURUSD", 9001) in bot.tracked_positions


def test_a_failed_orders_query_does_not_look_like_nothing_resting(tmp_path):
    """`orders_get()` breaking must not silently drop tracked orders --
    the same "can't tell means can't tell" rule that positions follow.

    Pins _weekend_is_close() -- see the comment on
    test_resting_order_survives_while_the_setup_is_merely_waiting.
    """
    fake = FakeMT5()
    bot, _, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))
    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._consider_entry("EURUSD", record, bot._account_state())

    fake.orders_get_raises = True
    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._reconcile_pending_entries(bot._account_state())

    assert len(bot.pending_entries) == 1  # still ours, still tracked


def test_resting_orders_count_toward_the_daily_risk_cap(tmp_path):
    """A resting order carries no risk until it fills -- but the worst
    case is that they ALL fill, within the same minute. Without this the
    same headroom gets handed out to every limit placed that day.
    """
    fake = FakeMT5()
    bot, audit, _ = _limit_bot(fake, tmp_path, instruments=("EURUSD",))

    # Four orders already resting, $1,000 of risk each, against a 4%
    # daily limit on a 100k account -- that is the entire day's headroom.
    from ..orchestrator import PendingEntry
    for i in range(4):
        bot.pending_entries[("EURUSD", 8000 + i)] = PendingEntry(
            row_id=i, instrument="EURUSD", ticket=8000 + i, risk_amount=1000.0,
            entry_price=1.17374, stop_loss=1.17290, target=1.17626,
            direction=Direction.BULLISH, signal_time=pd.Timestamp("2026-09-01T12:00Z"))

    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"), trade_id=99)
    with patch.object(LiveBot, "_candles_since", return_value=[]):
        bot._consider_entry("EURUSD", record, bot._account_state())

    # Declined, and no fifth order was sent.
    assert len(bot.pending_entries) == 4
    assert not any(c.get("action") == fake.TRADE_ACTION_PENDING
                   for c in fake.order_send_calls)
    row = audit.recent(1)[0]
    assert row["decision"] == "decline_daily_aggregate_risk"
    assert "resting order(s) as though already filled" in row["reason"]


# ---- weekend flatten: closing positions, not just cancelling orders ----

def test_flatten_closes_our_open_positions(tmp_path):
    fake = FakeMT5()
    bot, audit, _ = make_bot(fake, tmp_path)
    fake.positions = [
        make_position(ticket=101, symbol="EURUSD", price_open=1.1737, sl=1.1729, volume=0.5),
        make_position(ticket=102, symbol="EURUSD", price_open=1.1740, sl=1.1732, volume=0.3),
    ]

    bot._flatten_for_weekend(bot._account_state())

    assert fake.positions == []
    reasons = [r["reason"] for r in audit.recent(5)]
    assert all("weekend" in r for r in reasons)


def test_flatten_leaves_a_hand_placed_position_alone(tmp_path):
    """A position without our magic number is the operator's own trade.
    Closing someone else's position is not an undoable mistake."""
    fake = FakeMT5()
    bot, _, _ = make_bot(fake, tmp_path)
    fake.positions = [
        make_position(ticket=101, symbol="EURUSD", price_open=1.1737, sl=1.1729, volume=0.5),
        make_position(ticket=999, symbol="EURUSD", price_open=1.1700, sl=1.1690, volume=1.0,
                      magic=0),
    ]

    bot._flatten_for_weekend(bot._account_state())

    assert [p.ticket for p in fake.positions] == [999]


def test_flatten_closes_untracked_positions_that_are_ours(tmp_path):
    """The CHFJPY triple-fill case: they carry our magic but this process
    never recorded placing them, and they are exactly the positions most
    likely to be left sitting over a weekend."""
    fake = FakeMT5()
    bot, _, _ = make_bot(fake, tmp_path)
    fake.positions = [
        make_position(ticket=555, symbol="EURUSD", price_open=1.1737, sl=1.1729, volume=6.42),
    ]
    assert bot.tracked_positions == {}

    bot._flatten_for_weekend(bot._account_state())

    assert fake.positions == []


def test_flatten_escalates_rather_than_assuming_flat_when_it_cannot_read(tmp_path, caplog):
    """"Can't tell" must never read as "the account is flat"."""
    fake = FakeMT5()
    bot, _, _ = make_bot(fake, tmp_path)

    def boom(ticket=None):
        raise RuntimeError("bridge down")
    fake.positions_get = boom

    # state is unused on this path -- the read fails before it is touched.
    with caplog.at_level("ERROR"):
        bot._flatten_for_weekend(None)

    assert "CHECK BY HAND" in caplog.text


def test_close_position_is_a_deal_against_the_position_ticket():
    """MT5 has no close action -- it is an opposing DEAL carrying
    `position`, for the position's own broker-reported volume."""
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info()
    fake.positions = [make_position(ticket=77, symbol="EURUSD", price_open=1.1737,
                                     sl=1.1729, volume=0.42)]
    ex = MT5Execution(fake)

    result = ex.close_position(77)

    assert result.success
    req = fake.order_send_calls[-1]
    assert req["position"] == 77
    assert req["type"] == fake.ORDER_TYPE_SELL       # opposite of a long
    assert req["volume"] == 0.42                     # the broker's number


def test_close_position_treats_an_already_closed_position_as_success():
    fake = FakeMT5()
    ex = MT5Execution(fake)
    result = ex.close_position(12345)
    assert result.success
    assert "already closed" in result.reason
    assert fake.order_send_calls == []


def test_close_position_never_retries_an_ambiguous_close():
    """Re-sending a close against a position that already closed opens a
    NEW position the other way -- worse than the problem it would fix."""
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info()
    fake.positions = [make_position(ticket=77, symbol="EURUSD", price_open=1.1737,
                                     sl=1.1729, volume=0.42)]
    fake.positions[0].type = fake.POSITION_TYPE_BUY
    fake.order_send_queue = [
        SimpleNamespace(retcode=fake.TRADE_RETCODE_TIMEOUT, order=0, price=0.0, comment="timeout"),
    ]
    ex = MT5Execution(fake)

    result = ex.close_position(77)

    assert not result.success
    assert len(fake.order_send_calls) == 1
    assert "REVERSE position" in result.reason


def test_restart_does_not_report_cumulative_loss_as_todays_drawdown(tmp_path):
    """Confirmed live 2026-09-02: a restart logged "HALTED: daily drawdown
    breach: 6.86%" one second after starting, on an account that had lost
    nothing that day -- 6.86% was its loss since the phase began.

    `__post_init__` seeds day_start_balance with the PHASE start (100k),
    so the first _account_state() of a fresh process carries that seed;
    the health gate then read a cumulative drawdown as a daily one.
    """
    fake = FakeMT5()
    # Down 6.86% since the phase began, but flat on the day.
    fake.account = SimpleNamespace(balance=93140.0, equity=93140.0)
    bot, _, _ = make_bot(fake, tmp_path)

    bot.run_once()

    assert not bot.halted
    assert bot.day_start_balance == 93140.0


def test_a_genuine_daily_breach_still_halts(tmp_path):
    """The guard above must not blunt the real rule."""
    fake = FakeMT5()
    fake.account = SimpleNamespace(balance=100000.0, equity=100000.0)
    bot, _, _ = make_bot(fake, tmp_path)
    bot.run_once()                      # establishes today's baseline
    assert not bot.halted

    fake.account = SimpleNamespace(balance=94000.0, equity=94000.0)  # -6% today
    bot.run_once()
    assert bot.halted


def test_day_roll_snapshots_from_a_fresh_read_not_a_stale_first_one(tmp_path):
    """Confirmed live 2026-09-15: the bot had been disconnected from
    before midnight UTC through a reconnect at 01:07:52. That reconnect's
    OWN first account read -- the one that detects the day changed and
    used to be trusted as the snapshot -- returned a stale/cached balance
    ($103,499.33); a second read taken 8 seconds later in the SAME
    iteration correctly showed $92,860.85, the account's real, unchanged
    balance (confirmed against its actual trade history: zero deals in
    that entire window). Snapshotting from the first read manufactured a
    false 10.28% "daily drawdown" and halted the bot for the rest of the
    day on an account that hadn't moved at all.

    `_roll_day_if_needed()` must never trust the read that DETECTED the
    day change for the snapshot itself -- it has to re-fetch."""
    fake = FakeMT5()
    readings = iter([
        SimpleNamespace(balance=103499.33, equity=103499.33),  # stale, detects the roll
        SimpleNamespace(balance=92860.85, equity=92860.85),    # fresh re-fetch, the true value
    ])
    fallback = SimpleNamespace(balance=92860.85, equity=92860.85)
    fake.account_info = lambda: next(readings, fallback)
    bot, _, _ = make_bot(fake, tmp_path)

    bot.run_once()

    assert not bot.halted
    assert bot.day_start_balance == 92860.85


def test_limit_entry_declines_when_the_setup_cannot_be_verified(tmp_path):
    """An unreadable cache must not read as "nothing happened since the
    signal" -- that would rest an order against an unchecked thesis."""
    fake = FakeMT5()
    bot, audit, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))

    with patch.object(LiveBot, "_candles_since", return_value=None):
        bot._consider_entry("EURUSD", record, bot._account_state())

    assert bot.pending_entries == {}
    assert audit.recent(1)[0]["decision"] == "decline_setup_unverifiable"


def test_an_unverifiable_resting_order_is_left_alone_not_cancelled(tmp_path):
    """"Don't know" argues for doing nothing: the order sits at the right
    price and costs nothing while it waits.

    Pins _weekend_is_close() -- see the comment on
    test_resting_order_survives_while_the_setup_is_merely_waiting.
    """
    fake = FakeMT5()
    bot, _, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))
    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._consider_entry("EURUSD", record, bot._account_state())

    with patch.object(LiveBot, "_candles_since", return_value=None), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._reconcile_pending_entries(bot._account_state())

    assert len(bot.pending_entries) == 1
    assert len(fake.orders) == 1


def test_limit_mode_does_not_discard_signals_the_3h_market_cutoff_would(tmp_path):
    """The 3h gate sits BEFORE _consider_entry, so leaving it in front of
    the limit path would stop check_setup() ever running on the signals it
    exists to rescue -- the 2h+ bucket, 22 of the bot's 42 attempts.

    Caught live 2026-09-02: two EURCHF signals declined as "0 days
    07:00:00 old (cutoff 3:00:00)" an hour after limits were enabled.
    """
    fake = FakeMT5()
    bot, audit, _ = _limit_bot(fake, tmp_path)
    signal_time = pd.Timestamp("2026-09-02T07:00Z")
    record = a_trade_record(signal_time)

    state = bot._account_state()   # before mt5_client is mocked out
    bot._last_entry_time["EURUSD"] = signal_time - pd.Timedelta(hours=1)

    with gate_open(), \
         patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_consider_entry") as considered, \
         patch.object(bot, "mt5_client") as client, \
         patch("bot.orchestrator.sync_recent_from_mt5"), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        client.new_candle_closed.return_value = SimpleNamespace(
            time=signal_time + pd.Timedelta(hours=7))
        bot._check_instrument("EURUSD", state)

    # 7h old: over the 3h market cutoff, under the 24h limit backstop.
    considered.assert_called_once()


def test_market_mode_keeps_the_3h_cutoff(tmp_path):
    """A market-mode signal past STALE_ENTRY_CUTOFF must never take the
    PLAIN path to _consider_entry() (the one that can fire an immediate
    market order at a since-drifted price) -- 2026-09-15 revised: it is
    still routed to _consider_entry(), but with force_limit=True, which
    rests a limit at the original entry price instead of filling at
    market. See test_a_stale_market_signal_still_alive_by_price_rests_a_limit
    for the full behavioral test of that path."""
    fake = FakeMT5()
    bot, _, _ = make_bot(fake, tmp_path)          # market, the default
    signal_time = pd.Timestamp("2026-09-02T07:00Z")
    record = a_trade_record(signal_time)

    state = bot._account_state()   # before mt5_client is mocked out
    bot._last_entry_time["EURUSD"] = signal_time - pd.Timedelta(hours=1)

    with gate_open(), \
         patch.object(LiveBot, "_consider_entry") as considered, \
         patch.object(bot, "mt5_client") as client, \
         patch("bot.orchestrator.sync_recent_from_mt5"), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        client.new_candle_closed.return_value = SimpleNamespace(
            time=signal_time + pd.Timedelta(hours=7))
        bot._check_instrument("EURUSD", state)

    considered.assert_called_once_with("EURUSD", record, state, force_limit=True)


def test_limit_entry_declines_when_bias_no_longer_aligns_now(tmp_path):
    """The gap-replay gate passes a signal that hunted at ANY of the last
    72 candles, which is right for reporting a missed signal and wrong for
    resting an order: with a 24h window the thesis can have flipped, and
    check_setup() only looks at price, never bias.
    """
    fake = FakeMT5()
    bot, audit, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))
    bot._current_candle_time["EURUSD"] = pd.Timestamp("2026-09-02T10:00Z")

    with patch.object(LiveBot, "_storyline_says_hunt", return_value=False), \
         patch.object(LiveBot, "_candles_since", return_value=[]):
        bot._consider_entry("EURUSD", record, bot._account_state())

    assert bot.pending_entries == {}
    assert audit.recent(1)[0]["decision"] == "decline_bias_no_longer_aligned"


def test_limit_entry_proceeds_while_bias_still_aligns(tmp_path):
    fake = FakeMT5()
    bot, _, _ = _limit_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))
    bot._current_candle_time["EURUSD"] = pd.Timestamp("2026-09-02T10:00Z")

    with patch.object(LiveBot, "_storyline_says_hunt", return_value=True), \
         patch.object(LiveBot, "_candles_since", return_value=[]):
        bot._consider_entry("EURUSD", record, bot._account_state())

    assert len(bot.pending_entries) == 1


# ---- min_departure_r: deferred placement (added 2026-09-11) ----
# Extends the limit-order path so a resting order is only rested once
# price has genuinely left the entry level -- see setup_validity.py's
# check_setup() docstring for the backtest numbers that justify this, and
# why switching to trigger_wick without it would have picked the wrong
# stop anchor by the project's own data.

def _departure_bot(fake, tmp_path, instruments=("EURUSD",), min_departure_r=1.0):
    bot, audit, client = _limit_bot(fake, tmp_path, instruments)
    bot.min_departure_r = min_departure_r
    return bot, audit, client


def test_signal_that_has_not_departed_is_not_placed_yet(tmp_path):
    fake = FakeMT5()
    bot, audit, _ = _departure_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))

    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._consider_entry("EURUSD", record, bot._account_state())

    assert bot.pending_entries == {}
    assert fake.orders == []
    assert ("EURUSD", record.entry_time) in bot.awaiting_departure
    assert audit.recent(1)[0]["decision"] == "awaiting_departure"


def test_signal_is_placed_once_price_actually_departs(tmp_path):
    fake = FakeMT5()
    bot, audit, _ = _departure_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))

    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._consider_entry("EURUSD", record, bot._account_state())
    assert bot.awaiting_departure

    # risk = 1.17374 - 1.17290 = 0.00084; 1.0R away = 1.17458.
    departed = [_bar(high=1.17460, low=1.17380)]
    with patch.object(LiveBot, "_candles_since", return_value=departed), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._reconcile_awaiting_departure(bot._account_state())

    assert bot.awaiting_departure == {}
    assert len(bot.pending_entries) == 1
    assert len(fake.orders) == 1
    assert fake.order_send_calls[-1]["price"] == pytest.approx(round(record.entry_price, 4))
    assert audit.recent(1)[0]["decision"] == "allow_pending"


def test_awaiting_signal_dies_if_stop_breached_before_departing(tmp_path):
    """The move went straight through the invalidation point without ever
    proving itself first -- dead, never placed."""
    fake = FakeMT5()
    bot, audit, _ = _departure_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"), direction=Direction.BULLISH)

    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._consider_entry("EURUSD", record, bot._account_state())

    breached = [_bar(high=1.17300, low=1.17200)]  # through the 1.17290 stop
    with patch.object(LiveBot, "_candles_since", return_value=breached), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._reconcile_awaiting_departure(bot._account_state())

    assert bot.awaiting_departure == {}
    assert bot.pending_entries == {}
    assert fake.orders == []
    assert audit.recent(1)[0]["decision"] == "decline_setup_stop_breached"


def test_awaiting_signal_dies_if_bias_flips_while_waiting(tmp_path):
    fake = FakeMT5()
    bot, audit, _ = _departure_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))
    bot._current_candle_time["EURUSD"] = pd.Timestamp("2026-09-01T18:00Z")

    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_storyline_says_hunt", return_value=True), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._consider_entry("EURUSD", record, bot._account_state())
    assert bot.awaiting_departure

    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_storyline_says_hunt", return_value=False), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._reconcile_awaiting_departure(bot._account_state())

    assert bot.awaiting_departure == {}
    assert bot.pending_entries == {}
    assert audit.recent(1)[0]["decision"] == "decline_bias_no_longer_aligned"


def test_awaiting_signal_times_out_past_the_stale_limit_cutoff(tmp_path):
    fake = FakeMT5()
    bot, audit, _ = _departure_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))

    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._consider_entry("EURUSD", record, bot._account_state())
    assert bot.awaiting_departure

    bot._current_candle_time["EURUSD"] = record.entry_time + timedelta(hours=25)
    with patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._reconcile_awaiting_departure(bot._account_state())

    assert bot.awaiting_departure == {}
    assert bot.pending_entries == {}
    row = audit.recent(1)[0]
    assert row["decision"] == "decline_stale_signal"
    assert "25:00:00" in row["reason"] or "1 day" in row["reason"]


def test_awaiting_signal_is_dropped_not_placed_at_the_weekend_cutoff(tmp_path):
    fake = FakeMT5()
    bot, audit, _ = _departure_bot(fake, tmp_path)
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))

    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._consider_entry("EURUSD", record, bot._account_state())
    assert bot.awaiting_departure

    with patch.object(LiveBot, "_weekend_is_close", return_value=True):
        bot._reconcile_awaiting_departure(bot._account_state())

    assert bot.awaiting_departure == {}
    assert bot.pending_entries == {}
    assert fake.orders == []
    assert audit.recent(1)[0]["decision"] == "decline_weekend_close"


def test_min_departure_r_zero_places_immediately_unchanged(tmp_path):
    """The default must reproduce every limit-mode behavior from before
    2026-09-11 exactly -- nothing waits when min_departure_r is 0.0."""
    fake = FakeMT5()
    bot, audit, _ = _limit_bot(fake, tmp_path)   # min_departure_r defaults to 0.0
    record = a_trade_record(pd.Timestamp("2026-09-01T17:00Z"))

    with patch.object(LiveBot, "_candles_since", return_value=[]), \
         patch.object(LiveBot, "_weekend_is_close", return_value=False):
        bot._consider_entry("EURUSD", record, bot._account_state())

    assert bot.awaiting_departure == {}
    assert len(bot.pending_entries) == 1
    assert audit.recent(1)[0]["decision"] == "allow_pending"


def test_a_resting_entry_is_not_placed_while_halted(tmp_path):
    """_place_limit_entry has a second caller --
    _reconcile_awaiting_departure -- which runs BEFORE run_once()'s
    health gate. Guarding only _consider_entry would leave a signal
    already waiting for price to depart its level free to rest an order
    on a halted account, which is the one thing a halt exists to stop."""
    fake = FakeMT5()
    bot, audit, client = make_bot(tmp_path=tmp_path, fake=fake)
    bot.halted = True
    bot.halt_reason = "daily drawdown breach: 10.28% >= 4%"
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)
    state = client.account_state(100000.0, 100000.0)

    bot._place_limit_entry("EURUSD", record, state, 500.0, 0.10, "bullish", {})

    assert fake.order_send_calls == []
    rows = [r for r in audit.recent(10) if r["event_type"] == "entry_attempt"]
    assert rows and rows[0]["decision"] == "decline_account_halted"


# ---------------------------------------------------------------------------
# A market entry whose price ran away gets RESTED, not binned.
#
# 2026-09-17/18, after the cache repair cleared the stale signals, drift
# was 100% of the conservative bot's declines. Those refusals were
# correct -- a market order really would have filled at a price the stop
# was never sized for. Declining was right; declining and then doing
# nothing with a still-valid setup was the waste.
#
# Same rescue cedd67f already applies to a stale market signal.
# ---------------------------------------------------------------------------

def _runaway_price(fake, symbol="EURUSD"):
    info = make_symbol_info(point=0.0001)
    info.bid, info.ask = 1.3000, 1.3001   # miles from the signal's entry
    fake.symbols[symbol] = info


def test_a_drifted_market_entry_is_rested_as_a_limit(tmp_path):
    fake = FakeMT5()
    _runaway_price(fake)
    bot, audit, client = make_bot(fake, tmp_path)
    # Lives on the executor, not the bot -- make_bot's extras go to LiveBot.
    bot.mt5_exec._max_entry_drift_fraction = 1.0
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    decisions = [r["decision"] for r in audit.recent(20)
                 if r["event_type"] == "entry_attempt"]
    assert "reroute_drift_to_limit" in decisions, decisions
    # and it did not simply die there
    assert "decline_sizing_entry_price_drifted" not in decisions


def test_a_bot_already_resting_limits_is_not_rerouted(tmp_path):
    """Nothing to rescue -- the drift guard never ran for it in the first
    place, so there must be no reroute row muddying the log."""
    fake = FakeMT5()
    _runaway_price(fake)
    bot, audit, client = make_bot(fake, tmp_path, entry_order_type="limit")
    bot.mt5_exec._max_entry_drift_fraction = 1.0
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    decisions = [r["decision"] for r in audit.recent(20)
                 if r["event_type"] == "entry_attempt"]
    assert "reroute_drift_to_limit" not in decisions


def test_a_non_drift_sizing_failure_still_declines(tmp_path):
    """The reroute is for drift alone. A symbol that cannot be traded, or
    a stop the broker rejects, is not rescued by resting the order."""
    fake = FakeMT5()
    info = make_symbol_info(point=0.0001, trade_mode=0)  # not tradeable
    info.bid, info.ask = 1.1700, 1.1701
    fake.symbols["EURUSD"] = info
    bot, audit, client = make_bot(fake, tmp_path)
    bot.mt5_exec._max_entry_drift_fraction = 1.0
    entry_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    record = a_trade_record(entry_time)

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    decisions = [r["decision"] for r in audit.recent(20)
                 if r["event_type"] == "entry_attempt"]
    assert "reroute_drift_to_limit" not in decisions
    assert any(d.startswith("decline_sizing_") for d in decisions), decisions


def test_the_storyline_gate_is_given_the_same_flags_as_the_engine(tmp_path):
    """Regression for the 2026-09-18 review, finding 2.

    `build_htf_context()` used to be called as
    `build_htf_context(instrument, source=...)` and nothing else, so it
    fell back to its own defaults: a `valid_sweep_break` origin,
    wick-based sweep breaks and uncapped history. Both live bots run
    `--origin-kind any --close-based-sweep-break` with a history-windows
    config. A gate computing a different bias from the engine it gates is
    not a performance filter, it is a second, unmeasured strategy -- and
    it can refuse a candle at which run_backtest has a trade, which is
    the one thing live_strategy's docstring says it must never do.

    The real-data test in test_live_strategy.py now checks the deployed
    pairing end to end, but it SKIPS without a cache (gitignored, absent
    on a clean checkout), so it cannot be what guards this. This can: it
    asserts the wiring directly and runs everywhere."""
    fake = FakeMT5()
    windows = {"D": 2.0, "W": 2.0, "H4": 1.0, "H1": 1.0}
    bot, _audit, _client = make_bot(
        fake, tmp_path,
        origin_kind="any",
        close_based_sweep_break=True,
        history_window_years={"EURUSD": windows})

    seen = {}

    def spy(instrument, **kwargs):
        seen.update(kwargs)
        seen["instrument"] = instrument
        return None  # "no structure to bootstrap from" -- short-circuits the rest

    with patch("bot.orchestrator.build_htf_context", side_effect=spy), \
         patch.object(bot.mt5_client, "new_candle_closed", return_value=None):
        bot._storyline_says_hunt("EURUSD", pd.Timestamp("2026-09-18T12:00:00+00:00"))

    assert seen["instrument"] == "EURUSD"
    assert seen["origin_kind"] == "any"
    assert seen["close_based_sweep_break"] is True
    assert seen["max_history_years"] == windows


@contextmanager
def gate_closed():
    with patch.object(LiveBot, "_storyline_says_hunt", return_value=False):
        yield


def test_the_watermark_advances_while_the_gate_is_closed(tmp_path):
    """Regression for the 2026-09-18 review, finding 3.

    The WAITING path used to return without touching the watermark, so a
    closed gate accumulated and the eventual reopen emitted every signal
    since -- all past the cutoff, all declined stale. That is the burst
    pattern in the live audit database: quiet for 10-27 hours, then a
    cluster of declines, with CHFJPY's 09-09 and 09-12 signals both
    surfacing in the same burst on 09-16.
    """
    fake = FakeMT5()
    bot, audit, _ = make_bot(fake, tmp_path)

    waiting_candle = pd.Timestamp("2026-01-12T08:00:00+00:00")
    with patch.object(bot.mt5_client, "new_candle_closed") as new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_closed(), \
         patch("bot.orchestrator.run_backtest") as backtest:
        new_candle.return_value = type("C", (), {"time": waiting_candle})()
        bot.run_once()
        assert not backtest.called, "a closed gate must not run the entry search"

    assert bot._last_entry_time["EURUSD"] == waiting_candle

    # Now the gate opens two hours later. A signal stamped BEFORE the
    # waiting candle belongs to the span the gate already judged, and
    # must not resurface.
    reopened = pd.Timestamp("2026-01-12T10:00:00+00:00")
    during_the_wait = a_trade_record(pd.Timestamp("2026-01-12T05:00:00+00:00"), trade_id=1)
    after_reopen = a_trade_record(pd.Timestamp("2026-01-12T09:00:00+00:00"), trade_id=2)

    with patch.object(bot.mt5_client, "new_candle_closed") as new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest",
                return_value=[during_the_wait, after_reopen]):
        new_candle.return_value = type("C", (), {"time": reopened})()
        bot.run_once()

    considered = {r["trade_id"] for r in audit.recent(20)
                  if r["event_type"] == "entry_attempt"}
    assert "2" in considered, "the signal after the reopen should be considered"
    assert "1" not in considered, (
        "a signal from inside the WAITING span resurfaced -- the watermark "
        "did not advance while the gate was closed")


def test_a_recovered_watermark_is_bounded_by_the_limit_backstop(tmp_path):
    """The same flood by a second route.

    `_last_entry_time` is in memory only, so after a restart it is
    rebuilt from the audit database's last entry ATTEMPT -- and the
    WAITING path advances the in-memory watermark WITHOUT writing an
    attempt. So a bot that has been polling happily for a week comes back
    from a restart with a watermark a week old, and emits the lot.

    Bounded at the limit bot's own backstop: nothing actionable is ever
    outside it, and signals inside the window are untouched -- still
    reported one by one with the full strategy read, which is the part
    worth protecting.
    """
    fake = FakeMT5()
    bot, audit, _ = make_bot(fake, tmp_path)

    # Seed an attempt a week back, then drop the in-memory watermark as a
    # restart would.
    ancient = pd.Timestamp("2026-01-05T08:00:00+00:00")
    with patch.object(bot.mt5_client, "new_candle_closed") as new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest",
                return_value=[a_trade_record(ancient, trade_id=99)]):
        new_candle.return_value = type("C", (), {"time": ancient})()
        bot.run_once()
    assert audit.last_entry_time("EURUSD") is not None, "fixture did not seed an attempt"
    bot._last_entry_time.clear()

    now = pd.Timestamp("2026-01-12T08:00:00+00:00")   # a week later
    too_old = a_trade_record(now - timedelta(hours=30), trade_id=1)
    actionable = a_trade_record(now - timedelta(hours=2), trade_id=2)

    with patch.object(bot.mt5_client, "new_candle_closed") as new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), gate_open(), \
         patch("bot.orchestrator.run_backtest", return_value=[too_old, actionable]):
        new_candle.return_value = type("C", (), {"time": now})()
        bot.run_once()

    considered = {r["trade_id"] for r in audit.recent(20)
                  if r["event_type"] == "entry_attempt" and r["trade_id"] in ("1", "2")}
    assert "2" in considered, "a signal inside the backstop must still be evaluated"
    assert "1" not in considered, (
        "a 30h-old signal was evaluated -- the recovered watermark was not bounded")
