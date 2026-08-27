import csv
import os
import tempfile

import pandas as pd
import pytest

from ..structure import Direction
from ..trade_log import TradeRecord, write_trade_log, summarize


def T(hours):
    return pd.Timestamp("2024-01-01") + pd.Timedelta(hours=hours)


def make_record(trade_id, status, r_multiple=None, direction=Direction.BULLISH):
    return TradeRecord(
        trade_id=trade_id,
        instrument="EURUSD",
        entry_time=T(trade_id),
        exit_time=T(trade_id + 5),
        direction=direction,
        entry_timeframe="H1",
        entry_price=1.1000,
        entry_pattern="direct_mitigation",
        entry_style="conservative",
        trigger_type="engulfing",
        bias_daily=Direction.BULLISH,
        effective_bias_timeframe="Daily",
        key_level_price=1.0990,
        key_level_shape="V",
        imbalance_overlap=True,
        qmr_test_count=2,
        stop_loss=1.0980,
        stop_kind="engulfing",
        risk_pips=20,
        primary_target=1.1060,
        natural_stop_loss=1.0980,
        stop_fallback_used=False,
        raw_target=1.1120,
        erl_price=1.1060,
        erl_capped=True,
        exit_price=1.1060 if status == "closed_win" else 1.0980,
        exit_reason="target_hit" if status == "closed_win" else "stop_hit",
        r_multiple=r_multiple,
        status=status,
    )


def test_write_and_read_back_csv_roundtrip():
    records = [
        make_record(1, "closed_win", r_multiple=3.0),
        make_record(2, "closed_loss", r_multiple=-1.0),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "trades.csv")
        write_trade_log(records, path)

        with open(path) as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 2
        assert rows[0]["instrument"] == "EURUSD"
        assert rows[0]["direction"] == "bullish"        # Enum serialized to its .value
        assert rows[0]["bias_daily"] == "bullish"
        assert rows[0]["r_multiple"] == "3.0"
        assert "2024-01-01" in rows[0]["entry_time"]     # timestamp serialized to isoformat
        # Task 7's stop/target decision audit trail fields round-trip too.
        assert rows[0]["trigger_type"] == "engulfing"
        assert rows[0]["stop_fallback_used"] == "False"
        assert rows[0]["erl_price"] == "1.106"
        assert rows[0]["erl_capped"] == "True"


def test_write_trade_log_handles_empty_list_without_error():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "trades.csv")
        write_trade_log([], path)
        assert not os.path.exists(path)  # nothing written, nothing to error on


def test_summarize_computes_win_rate_and_total_r():
    records = [
        make_record(1, "closed_win", r_multiple=3.0),
        make_record(2, "closed_win", r_multiple=3.0),
        make_record(3, "closed_loss", r_multiple=-1.0),
        make_record(4, "open"),  # still open -- excluded from closed-trade stats
    ]

    summary = summarize(records)

    assert summary["total_trades"] == 4
    assert summary["closed_trades"] == 3
    assert summary["wins"] == 2
    assert summary["win_rate"] == pytest.approx(2 / 3)
    assert summary["total_r"] == pytest.approx(5.0)
    assert summary["avg_r"] == pytest.approx(5.0 / 3)


def test_summarize_handles_no_closed_trades():
    records = [make_record(1, "open")]
    summary = summarize(records)
    assert summary["win_rate"] is None
    assert summary["avg_r"] is None
