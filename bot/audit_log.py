"""
Durable, ML-training-oriented audit log for the live bot.

Every entry decision (allowed or declined, and why), every exit, and every
phase transition gets one row -- not just the financial bookkeeping (which
is all the offline account_audit_log.csv had), but the SAME strategy
feature vector backtest/engine/trade_log.py's TradeRecord captures (bias
states, trigger_type, key-level ranking factors, ERL info) PLUS the
execution-quality reality a backtest never has to deal with (requested vs.
filled price, spread at decision time, latency) PLUS the account-state
context the risk manager saw. The point: this data should be directly
usable to train a model later on "given this exact situation, what
happened" -- backtest data and live data share the same feature columns
on purpose, so the two datasets can eventually be combined rather than
needing to be reconciled after the fact.

SQLite, not CSV: a live bot needs to survive restarts without losing
rows mid-write, and needs a place to go back and fill in a trade's
OUTCOME once it closes (an entry decision and its eventual result are two
separate events in time) -- `update_outcome()` does that by row id.
Exporting to CSV for an external training pipeline is one query away
(`export_csv()`), so nothing about this format lands you back at
CSV-parsing figuring out data types.
"""

import csv
import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime, timezone


@dataclass
class DecisionRecord:
    event_type: str          # "entry_attempt" | "exit" | "phase_transition" | "health_halt"
    decision: str             # Decision.value from risk_manager.py, or "n/a" for phase_transition
    reason: str
    timestamp: str = ""       # ISO8601 UTC; auto-filled by AuditLog.append() if left blank
    instrument: str = ""
    trade_id: str = ""        # MT5 position ticket, once assigned
    risk_amount: float = 0.0

    # Strategy feature context -- mirrors backtest/engine/trade_log.py's
    # TradeRecord field-for-field on purpose (see module docstring).
    #
    # entry_time (added 2026-08-29) is the SIGNAL's own candle close time
    # -- NOT the same thing as `timestamp` above, which is when this row
    # was written. They can differ by hours: the watermark-widening fix
    # (2026-08-28) and the storyline-gap-replay fix (2026-08-29) both
    # legitimately let a poll evaluate and act on an OLDER candle than
    # the one that just closed, after catching up from an outage. Without
    # this field there was no way to tell "a fresh signal that happened
    # to fail" from "a stale catch-up of an old one" after the fact --
    # exactly the question raised, and un-answerable from the rows
    # written before this field existed.
    entry_time: str = ""
    direction: str = ""
    entry_timeframe: str = ""
    entry_price: float | None = None
    entry_pattern: str = ""
    trigger_type: str = ""
    bias_monthly: str = ""
    bias_weekly: str = ""
    bias_daily: str = ""
    bias_h4: str = ""
    bias_h1: str = ""
    effective_bias_timeframe: str = ""
    aligned_timeframes: str = ""
    key_level_price: float | None = None
    key_level_shape: str = ""
    ranking_score: float | None = None
    stop_loss: float | None = None
    stop_kind: str = ""
    primary_target: float | None = None
    erl_price: float | None = None
    erl_capped: bool = False

    # Execution-quality context -- what a backtest never has to model.
    requested_price: float | None = None
    filled_price: float | None = None
    slippage_points: float | None = None
    spread_at_decision: float | None = None
    latency_ms: float | None = None

    # Account-state context the risk manager saw at this exact moment.
    phase: str = ""
    balance: float | None = None
    equity: float | None = None
    day_start_balance: float | None = None
    phase_start_balance: float | None = None
    open_positions_count: int = 0
    open_risk_total: float = 0.0
    daily_dd_pct: float | None = None
    overall_dd_pct: float | None = None

    # Outcome -- unknown at entry time, filled in later via update_outcome().
    exit_price: float | None = None
    exit_reason: str | None = None
    r_multiple: float | None = None
    realized_pnl: float | None = None
    mae_r: float | None = None
    mfe_r: float | None = None


_FIELD_NAMES = [f.name for f in fields(DecisionRecord)]
_COLUMN_TYPES = {
    "risk_amount": "REAL", "entry_price": "REAL", "key_level_price": "REAL",
    "ranking_score": "REAL", "stop_loss": "REAL", "primary_target": "REAL", "erl_price": "REAL",
    "erl_capped": "INTEGER", "requested_price": "REAL", "filled_price": "REAL",
    "slippage_points": "REAL", "spread_at_decision": "REAL", "latency_ms": "REAL",
    "balance": "REAL", "equity": "REAL", "day_start_balance": "REAL", "phase_start_balance": "REAL",
    "open_positions_count": "INTEGER", "open_risk_total": "REAL",
    "daily_dd_pct": "REAL", "overall_dd_pct": "REAL",
    "exit_price": "REAL", "r_multiple": "REAL", "realized_pnl": "REAL", "mae_r": "REAL", "mfe_r": "REAL",
}


class AuditLog:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self):
        columns_sql = ", ".join(
            f'"{name}" {_COLUMN_TYPES.get(name, "TEXT")}' for name in _FIELD_NAMES
        )
        self._conn.execute(f"CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, {columns_sql})")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_instrument_trade ON decisions (instrument, trade_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions (timestamp)")
        self._migrate_missing_columns()
        self._conn.commit()

    def _migrate_missing_columns(self):
        """CREATE TABLE IF NOT EXISTS is a no-op against a table that
        already exists -- confirmed live 2026-08-29: adding entry_time to
        DecisionRecord did nothing for any already-running bot's existing
        audit.db, and every single append() (allow, decline, execution_
        failed -- ALL of them) started raising `sqlite3.OperationalError:
        table decisions has no column named entry_time`, uncaught up
        through _check_instrument's per-instrument exception isolation --
        which ALSO meant _last_entry_time never advanced, so the same
        signal would have been retried and crashed again every single
        poll, forever, until this was fixed. A schema field can be added
        again in the future; this makes that safe by construction instead
        of relying on remembering to write a migration each time."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(decisions)")}
        for name in _FIELD_NAMES:
            if name not in existing:
                col_type = _COLUMN_TYPES.get(name, "TEXT")
                self._conn.execute(f'ALTER TABLE decisions ADD COLUMN "{name}" {col_type}')

    def append(self, record: DecisionRecord) -> int:
        if not record.timestamp:
            record.timestamp = datetime.now(timezone.utc).isoformat()
        row = {name: getattr(record, name) for name in _FIELD_NAMES}
        row["erl_capped"] = int(bool(row["erl_capped"]))
        placeholders = ", ".join(f":{name}" for name in _FIELD_NAMES)
        columns = ", ".join(f'"{name}"' for name in _FIELD_NAMES)
        cur = self._conn.execute(f"INSERT INTO decisions ({columns}) VALUES ({placeholders})", row)
        self._conn.commit()
        return cur.lastrowid

    def update_outcome(self, row_id: int, exit_price: float, exit_reason: str,
                        r_multiple: float, realized_pnl: float,
                        mae_r: float | None = None, mfe_r: float | None = None):
        self._conn.execute(
            "UPDATE decisions SET exit_price=?, exit_reason=?, r_multiple=?, realized_pnl=?, mae_r=?, mfe_r=? WHERE id=?",
            (exit_price, exit_reason, r_multiple, realized_pnl, mae_r, mfe_r, row_id),
        )
        self._conn.commit()

    def find_open_entry_row(self, instrument: str, trade_id: str) -> int | None:
        """Looks up the row id of the entry_attempt/accepted decision for
        a given (instrument, trade_id) so its outcome can be filled in
        once MT5 reports the position closed."""
        cur = self._conn.execute(
            "SELECT id FROM decisions WHERE instrument=? AND trade_id=? AND event_type='entry_attempt' "
            "AND decision='allow' AND exit_reason IS NULL ORDER BY id DESC LIMIT 1",
            (instrument, trade_id),
        )
        row = cur.fetchone()
        return row["id"] if row else None

    def last_entry_time(self, instrument: str) -> str | None:
        """The signal-candle time (DecisionRecord.entry_time, a string --
        see that field's own comment) of the most recent entry_attempt
        logged for this instrument, or None if nothing has ever been
        logged for it.

        Confirmed live 2026-08-30/31: orchestrator.py's _last_entry_time
        watermark lives only in memory, so every process restart resets
        it to cold-start (exact-match-only), and any signal that closed
        around a restart -- one of the most common times for a restart
        to happen, since a deploy is exactly when this bot gets
        restarted -- was silently and permanently lost, with no audit
        row at all: a Dukascopy-reference comparison the same day found
        9 of 11 signals with zero trace in either audit database. This
        lets the orchestrator reconstruct a real watermark from what was
        already durably logged instead of starting blind every time."""
        cur = self._conn.execute(
            "SELECT entry_time FROM decisions WHERE instrument=? AND event_type='entry_attempt' "
            "AND entry_time != '' ORDER BY id DESC LIMIT 1",
            (instrument,),
        )
        row = cur.fetchone()
        return row["entry_time"] if row else None

    def entry_times_since(self, instrument: str, since: str) -> list[str]:
        """Every distinct signal-candle time this instrument has already
        had an entry_attempt logged for, at or after `since` (both plain
        ISO strings -- see DecisionRecord.entry_time's own comment).

        The single `last_entry_time()` above is enough for a strict
        watermark, but not for the grace margin the orchestrator now
        applies: `signal_known_at` is an estimate, so the selection
        window deliberately reaches back BEHIND the watermark to catch a
        signal born later than predicted. That re-exposes every signal in
        the margin, including ones a previous process already declined --
        which is the live-confirmed duplicate-decline bug of 2026-09-15
        (JP225's 02:00 signal declined twice, bracketing that day's two
        restarts). A fresh process seeds its dedupe set from this."""
        cur = self._conn.execute(
            "SELECT DISTINCT entry_time FROM decisions WHERE instrument=? "
            "AND event_type='entry_attempt' AND entry_time != '' AND entry_time >= ?",
            (instrument, since),
        )
        return [row["entry_time"] for row in cur.fetchall()]

    def export_csv(self, path: str):
        cur = self._conn.execute("SELECT * FROM decisions ORDER BY id")
        rows = cur.fetchall()
        if not rows:
            return
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

    def recent(self, limit: int = 50) -> list[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))
        return cur.fetchall()

    def close(self):
        self._conn.close()
