"""Tests for compare_history_window.py -- the tool that checks whether a
bounded trailing candle window reproduces the same recent trades full
history does.

Two layers: pure unit tests of `windowed_loader()`/`diff_recent()` against
fabricated data, and a couple of true end-to-end tests reusing
test_runner.py's own `synthetic_cache` fixture to confirm the monkeypatch
actually changes what `run_backtest()` sees.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from backtest.engine.candles import Candle
from backtest.engine.structure import Direction
from backtest.engine.trade_log import TradeRecord
from backtest.engine.tests.test_runner import SOURCE, SYMBOL, synthetic_cache  # noqa: F401 -- fixture
from backtest.tools.compare_history_window import diff_recent, run_variant, windowed_loader


def _candle(day_offset, o=1.0, h=1.0, l=1.0, c=1.0):
    return Candle(pd.Timestamp("2023-01-01") + pd.Timedelta(days=day_offset), o, h, l, c, 100.0)


def _long_series(days=3 * 365):
    return [_candle(i) for i in range(days)]


def test_windowed_loader_trims_to_the_trailing_window():
    series = _long_series()
    with patch("backtest.tools.compare_history_window.real_load_candles", return_value=series):
        loader = windowed_loader({"D": 365})
        result = loader("dukascopy", "EURUSD", "D")
    assert result[0].time == series[-1].time - pd.Timedelta(days=365)
    assert result[-1].time == series[-1].time
    assert len(result) == 366  # inclusive of both ends


def test_windowed_loader_extends_the_cutoff_by_recent_days():
    """The regression this test locks in: a trade dated `recent_days` old
    must still see a full `window`-day runway ending AT ITS OWN time, not
    a `window`-day runway ending at TODAY (which would leave it with
    almost nothing). Caught directly by the operator: "for a trade 2
    years ago it will start from 4 years ago" -- window (2y) + recency
    (2y), not window alone."""
    series = _long_series(days=5 * 365)
    with patch("backtest.tools.compare_history_window.real_load_candles", return_value=series):
        loader = windowed_loader({"D": 365 * 2}, recent_days=365 * 2)
        result = loader("dukascopy", "EURUSD", "D")

    oldest_time_in_comparison_period = series[-1].time - pd.Timedelta(days=365 * 2)
    runway_before_it = [c for c in result if c.time <= oldest_time_in_comparison_period]
    # A full 2-year runway ending exactly at that trade's own time.
    assert runway_before_it[0].time == oldest_time_in_comparison_period - pd.Timedelta(days=365 * 2)
    assert runway_before_it[-1].time == oldest_time_in_comparison_period


def test_windowed_loader_passes_through_a_granularity_with_no_configured_window():
    series = _long_series()
    with patch("backtest.tools.compare_history_window.real_load_candles", return_value=series):
        loader = windowed_loader({"D": 365})   # H1 not configured
        result = loader("dukascopy", "EURUSD", "H1")
    assert result == series


def test_windowed_loader_is_a_noop_when_the_window_is_bigger_than_the_data():
    series = _long_series(days=30)
    with patch("backtest.tools.compare_history_window.real_load_candles", return_value=series):
        loader = windowed_loader({"D": 365 * 5})
        result = loader("dukascopy", "EURUSD", "D")
    assert result == series


def test_windowed_loader_handles_an_empty_series():
    with patch("backtest.tools.compare_history_window.real_load_candles", return_value=[]):
        loader = windowed_loader({"D": 365})
        assert loader("dukascopy", "EURUSD", "D") == []


def _trade(entry_time, instrument="EURUSD", entry_price=1.1, r_multiple=1.0, status="closed_win"):
    return TradeRecord(
        trade_id=1, instrument=instrument, entry_time=entry_time,
        direction=Direction.BULLISH, entry_price=entry_price, stop_loss=1.09,
        primary_target=1.13, trigger_type="engulfing", exit_reason="target_hit",
        r_multiple=r_multiple, status=status,
    )


def test_diff_recent_identical_runs_have_no_mismatches():
    t = _trade(pd.Timestamp("2026-06-01"))
    result = diff_recent([t], [t], recent_cutoff=pd.Timestamp("2026-01-01"))
    assert result == {
        "baseline_count": 1, "variant_count": 1, "matched": 1,
        "only_in_baseline": [], "only_in_variant": [],
    }


def test_diff_recent_flags_a_trade_missing_from_the_truncated_run():
    baseline = [_trade(pd.Timestamp("2026-06-01"))]
    variant = []
    result = diff_recent(baseline, variant, recent_cutoff=pd.Timestamp("2026-01-01"))
    assert result["matched"] == 0
    assert result["only_in_baseline"] == baseline
    assert result["only_in_variant"] == []


def test_diff_recent_flags_a_trade_only_the_truncated_run_produced():
    baseline = []
    variant = [_trade(pd.Timestamp("2026-06-01"))]
    result = diff_recent(baseline, variant, recent_cutoff=pd.Timestamp("2026-01-01"))
    assert result["only_in_variant"] == variant


def test_diff_recent_ignores_trades_before_the_cutoff_even_if_they_differ():
    old_baseline = _trade(pd.Timestamp("2020-01-01"), r_multiple=1.0)
    old_variant = _trade(pd.Timestamp("2020-01-01"), r_multiple=-1.0)   # would mismatch if compared
    result = diff_recent([old_baseline], [old_variant], recent_cutoff=pd.Timestamp("2026-01-01"))
    assert result == {
        "baseline_count": 0, "variant_count": 0, "matched": 0,
        "only_in_baseline": [], "only_in_variant": [],
    }


def test_a_generous_window_reproduces_the_fixture_exactly(synthetic_cache):
    """The fixture's whole H1/H4/Daily span is under a month -- a 5-year
    window can't possibly cut anything, so this must reproduce the
    unpatched baseline bit-for-bit. Confirms the patch mechanism itself
    doesn't change behavior when it shouldn't."""
    baseline, _ = run_variant(SYMBOL, "conservative", "trigger_wick", None,
                               source=SOURCE, pip_size=0.0001)
    variant, _ = run_variant(SYMBOL, "conservative", "trigger_wick",
                              {"D": 365 * 5, "W": 365 * 5, "H4": 365 * 5, "H1": 365 * 5},
                              source=SOURCE, pip_size=0.0001)
    assert len(baseline) == 1
    result = diff_recent(baseline, variant, recent_cutoff=pd.Timestamp("2000-01-01"))
    assert result["only_in_baseline"] == []
    assert result["only_in_variant"] == []
    assert result["matched"] == 1


def test_a_window_too_short_to_see_the_origin_breakout_loses_the_trade(synthetic_cache):
    """The fixture's whole thesis depends on Daily's day-8 breakout --
    windowing Daily down to a single day cannot see it, so
    run_backtest() finds no confirmed structure to bootstrap a bias from
    (see runner.py's own `if first_origin is None: return []`) and
    produces nothing. This is the tool correctly detecting a REAL
    divergence, not a test that only ever finds everything identical."""
    variant, _ = run_variant(SYMBOL, "conservative", "trigger_wick",
                              {"D": 1, "W": 1, "H4": 1, "H1": 1},
                              source=SOURCE, pip_size=0.0001)
    assert variant == []
