from unittest.mock import patch

import pandas as pd
import pytest

from backtest.engine.structure import Direction
from backtest.engine.trade_log import TradeRecord

from .fake_mt5 import FakeMT5, make_position, make_symbol_info, make_deal
from ..audit_log import AuditLog, DecisionRecord
from ..config import AccountProfile, MT5Credentials, PhaseConfig, PhaseRules
from ..mt5_data import MT5Client
from ..mt5_execution import MT5Execution
from ..orchestrator import LiveBot, TrackedPosition

RULES = PhaseRules(daily_dd_limit_pct=0.04, overall_dd_limit_pct=0.10,
                    risk_normal=1000.0, risk_reduced=500.0, de_risk_at_pct=0.05,
                    profit_target_pct=0.08)
CREDS = MT5Credentials(login=1, password="pw", server="Demo")


def make_profile():
    return AccountProfile(account_type="prop_firm", active_phase="phase1",
                           phases={"phase1": PhaseConfig(rules=RULES, credentials=CREDS)})


def make_bot(fake, tmp_path, instruments=("EURUSD",)):
    fake.symbols.setdefault("EURUSD", make_symbol_info(point=0.0001))
    client = MT5Client(fake, login=1, password="pw", server="Demo")
    client.connect()
    execu = MT5Execution(fake)
    audit = AuditLog(str(tmp_path / "audit.db"))
    return LiveBot(profile=make_profile(), mt5_client=client, mt5_exec=execu,
                    audit_log=audit, instruments=instruments), audit, client


def a_trade_record(entry_time, trade_id=1, direction=Direction.BULLISH):
    return TradeRecord(
        trade_id=trade_id, instrument="EURUSD", entry_time=entry_time,
        direction=direction, entry_timeframe="H1", entry_price=1.17374,
        stop_loss=1.17290, primary_target=1.17626,
        trigger_type="engulfing", trade_kind="origin",
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


def test_run_once_skips_iteration_when_account_state_fetch_fails(tmp_path):
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)
    fake.account = None  # account_info() will return None -> MT5ConnectionError

    bot.run_once()
    assert audit.recent(10) == []


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
         patch("bot.orchestrator.sync_recent_from_mt5"), \
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
         patch("bot.orchestrator.sync_recent_from_mt5"), \
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
         patch("bot.orchestrator.sync_recent_from_mt5"), \
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
         patch("bot.orchestrator.sync_recent_from_mt5"), \
         patch("bot.orchestrator.run_backtest", return_value=[record]):
        mock_new_candle.return_value = type("C", (), {"time": entry_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert rows[0]["decision"].startswith("decline_sizing_")
    assert fake.order_send_calls == []
    assert bot.tracked_positions == {}


def test_only_the_record_matching_the_new_candles_time_is_considered(tmp_path):
    fake = FakeMT5()
    bot, audit, client = make_bot(fake, tmp_path)

    new_time = pd.Timestamp("2026-01-13T14:00:00+00:00")
    old_time = pd.Timestamp("2026-01-10T09:00:00+00:00")
    records = [a_trade_record(old_time, trade_id=1), a_trade_record(new_time, trade_id=2)]

    with patch.object(bot.mt5_client, "new_candle_closed") as mock_new_candle, \
         patch("bot.orchestrator.sync_recent_from_mt5"), \
         patch("bot.orchestrator.run_backtest", return_value=records):
        mock_new_candle.return_value = type("C", (), {"time": new_time})()
        bot.run_once()

    rows = audit.recent(10)
    assert len(rows) == 1
    assert rows[0]["trade_id"] == "2"


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
