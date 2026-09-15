import sqlite3

import pandas as pd
import pytest

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..analyze_stale_declines import evaluate, fetch_stale_declines


def _make_db(tmp_path, rows):
    path = str(tmp_path / "audit.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE decisions (timestamp TEXT, event_type TEXT, decision TEXT, "
        "instrument TEXT, entry_time TEXT, direction TEXT, entry_price REAL, "
        "stop_loss REAL, primary_target REAL, entry_pattern TEXT, trigger_type TEXT)"
    )
    for row in rows:
        conn.execute(
            "INSERT INTO decisions (timestamp, event_type, decision, instrument, entry_time, "
            "direction, entry_price, stop_loss, primary_target, entry_pattern, trigger_type) "
            "VALUES (:timestamp, 'entry_attempt', :decision, :instrument, :entry_time, :direction, "
            ":entry_price, :stop_loss, :primary_target, 'fourth_man', 'wick')",
            row,
        )
    conn.commit()
    conn.close()
    return path


def _row(**over):
    base = dict(timestamp="2026-09-15T05:00:00+00:00", decision="decline_stale_signal",
                instrument="EURUSD", entry_time="2026-09-15T01:00:00+00:00", direction="bullish",
                entry_price=1.1000, stop_loss=1.0980, primary_target=1.1060)
    base.update(over)
    return base


def test_fetch_stale_declines_reads_only_that_decision(tmp_path):
    db = _make_db(tmp_path, [_row(), _row(decision="allow")])
    rows = fetch_stale_declines(db)
    assert len(rows) == 1
    assert rows[0]["instrument"] == "EURUSD"


def test_evaluate_reports_alive_when_price_never_moved(tmp_path, monkeypatch):
    row = _row()
    candles = [Candle(pd.Timestamp("2026-09-15T02:00:00Z"), 1.1000, 1.1005, 1.0995, 1.1002, 100)]
    monkeypatch.setattr("backtest.tools.analyze_stale_declines.load_candles", lambda *a, **k: candles)

    verdict = evaluate(row)

    assert verdict.alive


def test_evaluate_reports_stop_breached_when_price_already_invalidated_it(tmp_path, monkeypatch):
    row = _row()  # bullish, stop 1.0980
    candles = [Candle(pd.Timestamp("2026-09-15T02:00:00Z"), 1.1000, 1.1005, 1.0970, 1.0975, 100)]
    monkeypatch.setattr("backtest.tools.analyze_stale_declines.load_candles", lambda *a, **k: candles)

    verdict = evaluate(row)

    assert not verdict.alive
    assert "STOP_BREACHED" in verdict.validity.name or verdict.validity.value == "stop_breached"


def test_evaluate_only_considers_candles_between_signal_and_decline_time(tmp_path, monkeypatch):
    """A candle AFTER the decline was logged must not count -- that price
    action hadn't happened yet at the moment the bot actually declined it."""
    row = _row()  # decline logged at 05:00, stop 1.0980
    candles = [
        Candle(pd.Timestamp("2026-09-15T02:00:00Z"), 1.1000, 1.1005, 1.0995, 1.1002, 100),
        # This breach happens AFTER the decline timestamp -- must be excluded.
        Candle(pd.Timestamp("2026-09-15T06:00:00Z"), 1.1000, 1.1005, 1.0900, 1.0950, 100),
    ]
    monkeypatch.setattr("backtest.tools.analyze_stale_declines.load_candles", lambda *a, **k: candles)

    verdict = evaluate(row)

    assert verdict.alive


def test_evaluate_returns_none_when_cache_is_missing(monkeypatch):
    def _raise(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr("backtest.tools.analyze_stale_declines.load_candles", _raise)

    assert evaluate(_row()) is None


def test_evaluate_handles_bearish_direction(monkeypatch):
    row = _row(direction="bearish", entry_price=1.1000, stop_loss=1.1020, primary_target=1.0940)
    candles = [Candle(pd.Timestamp("2026-09-15T02:00:00Z"), 1.1000, 1.1030, 1.0995, 1.1025, 100)]
    monkeypatch.setattr("backtest.tools.analyze_stale_declines.load_candles", lambda *a, **k: candles)

    verdict = evaluate(row)

    assert verdict.validity.value == "stop_breached"
