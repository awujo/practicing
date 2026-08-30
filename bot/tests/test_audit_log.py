import csv
import os
import sqlite3

import pytest

from ..audit_log import AuditLog, DecisionRecord


@pytest.fixture
def log(tmp_path):
    db_path = str(tmp_path / "audit.db")
    al = AuditLog(db_path)
    yield al
    al.close()


def test_append_returns_an_incrementing_row_id(log):
    r1 = log.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok"))
    r2 = log.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok"))
    assert r2 == r1 + 1


def test_append_auto_fills_timestamp_when_blank(log):
    row_id = log.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok"))
    row = log.recent(1)[0]
    assert row["timestamp"]  # non-empty
    assert row["id"] == row_id


def test_append_preserves_a_caller_supplied_timestamp(log):
    log.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok",
                               timestamp="2026-01-13T14:00:00+00:00"))
    row = log.recent(1)[0]
    assert row["timestamp"] == "2026-01-13T14:00:00+00:00"


def test_full_entry_context_round_trips_correctly(log):
    record = DecisionRecord(
        event_type="entry_attempt", decision="allow", reason="passed all gates",
        instrument="EURUSD", trade_id="1", risk_amount=1000.0,
        direction="bullish", entry_timeframe="H1", entry_price=1.17374,
        trigger_type="engulfing", bias_weekly="bullish", aligned_timeframes="Weekly,Daily,H4",
        erl_price=1.18482, erl_capped=False,
        phase="phase1", balance=100000.0, equity=100000.0,
        day_start_balance=100000.0, phase_start_balance=100000.0,
        open_positions_count=2, open_risk_total=2000.0,
        daily_dd_pct=0.01, overall_dd_pct=0.0,
    )
    log.append(record)
    row = log.recent(1)[0]
    assert row["instrument"] == "EURUSD"
    assert row["entry_price"] == 1.17374
    assert row["trigger_type"] == "engulfing"
    assert row["erl_capped"] == 0  # stored as INTEGER
    assert row["open_positions_count"] == 2
    assert row["daily_dd_pct"] == 0.01


def test_update_outcome_fills_in_the_result_after_a_trade_closes(log):
    row_id = log.append(DecisionRecord(
        event_type="entry_attempt", decision="allow", reason="ok",
        instrument="EURUSD", trade_id="1",
    ))
    log.update_outcome(row_id, exit_price=1.1762, exit_reason="target_hit",
                        r_multiple=3.0, realized_pnl=3000.0, mae_r=-0.5, mfe_r=3.2)
    row = log.recent(1)[0]
    assert row["exit_reason"] == "target_hit"
    assert row["r_multiple"] == 3.0
    assert row["realized_pnl"] == 3000.0


def test_find_open_entry_row_locates_the_matching_accepted_entry(log):
    row_id = log.append(DecisionRecord(
        event_type="entry_attempt", decision="allow", reason="ok",
        instrument="GBPUSD", trade_id="7",
    ))
    found = log.find_open_entry_row("GBPUSD", "7")
    assert found == row_id


def test_find_open_entry_row_ignores_declined_entries(log):
    log.append(DecisionRecord(event_type="entry_attempt", decision="decline_daily_aggregate_risk",
                               reason="blocked", instrument="GBPUSD", trade_id="8"))
    assert log.find_open_entry_row("GBPUSD", "8") is None


def test_find_open_entry_row_ignores_already_closed_trades(log):
    row_id = log.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok",
                                        instrument="GBPUSD", trade_id="9"))
    log.update_outcome(row_id, exit_price=1.3, exit_reason="stop_hit", r_multiple=-1.0, realized_pnl=-1000.0)
    assert log.find_open_entry_row("GBPUSD", "9") is None


def test_export_csv_writes_every_row_with_headers(log, tmp_path):
    log.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok", instrument="EURUSD"))
    log.append(DecisionRecord(event_type="exit", decision="n/a", reason="closed", instrument="EURUSD"))
    out_path = str(tmp_path / "export.csv")
    log.export_csv(out_path)
    with open(out_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["instrument"] == "EURUSD"


def test_export_csv_on_an_empty_log_does_not_crash(log, tmp_path):
    out_path = str(tmp_path / "export.csv")
    log.export_csv(out_path)
    assert not os.path.exists(out_path)


def test_audit_log_survives_reopening_the_same_db_file(tmp_path):
    db_path = str(tmp_path / "audit.db")
    al1 = AuditLog(db_path)
    al1.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok", instrument="EURUSD"))
    al1.close()

    al2 = AuditLog(db_path)
    rows = al2.recent(10)
    al2.close()
    assert len(rows) == 1
    assert rows[0]["instrument"] == "EURUSD"


def test_opening_a_db_with_an_older_schema_adds_the_missing_columns(tmp_path):
    # Confirmed live 2026-08-29: CREATE TABLE IF NOT EXISTS is a no-op
    # against a table that already exists. Adding entry_time to
    # DecisionRecord did nothing for a bot process already running
    # against an existing audit.db from before that field existed -- every
    # single append() (allow, decline, execution_failed, all of them)
    # started raising sqlite3.OperationalError, uncaught up through
    # _check_instrument's exception isolation, which ALSO meant
    # _last_entry_time never advanced -- so the exact same signal would
    # have been retried and crashed again on every subsequent poll,
    # forever. This reproduces the exact scenario: a real db file created
    # with an OLDER schema (missing a column current code expects), then
    # opened by current code -- must self-heal, not crash.
    db_path = str(tmp_path / "old_schema.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                  'event_type TEXT, decision TEXT, reason TEXT, timestamp TEXT, '
                  'instrument TEXT, trade_id TEXT, risk_amount REAL)')
    conn.commit()
    conn.close()

    al = AuditLog(db_path)  # must not raise
    row_id = al.append(DecisionRecord(event_type="entry_attempt", decision="allow", reason="ok",
                                       instrument="EURUSD", entry_time="2026-08-29T14:00:00+00:00"))
    row = al.recent(1)[0]
    al.close()
    assert row["id"] == row_id
    assert row["entry_time"] == "2026-08-29T14:00:00+00:00"
