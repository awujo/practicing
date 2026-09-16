"""Tests for the liquidity-mode A/B tool's own logic.

The tool's value is entirely in correctly identifying which trades exist
under one mode and not the other -- if the windowing or the cross-mode
key is wrong, the "check this pair by hand" list it prints is wrong, and
that list is what gets acted on. The backtest itself is covered by the
engine's tests; these cover the comparison layer.
"""

import pandas as pd
import pytest

from ..compare_liquidity_modes import _in_window, _key, _fmt_price


class _Rec:
    def __init__(self, instrument, direction, entry_time):
        self.instrument = instrument
        self.direction = direction
        self.entry_time = entry_time


def test_window_is_inclusive_at_both_ends():
    start = pd.Timestamp("2026-09-08", tz="UTC")
    end = pd.Timestamp("2026-09-16", tz="UTC")
    assert _in_window(_Rec("EURUSD", "bull", start), start, end)
    assert _in_window(_Rec("EURUSD", "bull", end), start, end)


def test_trades_outside_the_window_are_excluded():
    start = pd.Timestamp("2026-09-08", tz="UTC")
    end = pd.Timestamp("2026-09-16", tz="UTC")
    before = pd.Timestamp("2026-09-07 23:00", tz="UTC")
    after = pd.Timestamp("2026-09-16 01:00", tz="UTC")
    assert not _in_window(_Rec("EURUSD", "bull", before), start, end)
    assert not _in_window(_Rec("EURUSD", "bull", after), start, end)


def test_no_bounds_keeps_everything():
    t = pd.Timestamp("2020-01-01", tz="UTC")
    assert _in_window(_Rec("EURUSD", "bull", t), None, None)


def test_naive_entry_times_do_not_blow_up_the_run():
    """A naive/aware comparison raises in pandas. Treat naive as UTC
    rather than aborting a multi-instrument run over a tz detail."""
    start = pd.Timestamp("2026-09-08", tz="UTC")
    naive = pd.Timestamp("2026-09-10 12:00")
    assert _in_window(_Rec("EURUSD", "bull", naive), start, None)


def test_key_distinguishes_instrument_side_and_entry_candle():
    t = pd.Timestamp("2026-09-10 12:00", tz="UTC")
    other = pd.Timestamp("2026-09-10 13:00", tz="UTC")
    base = _key(_Rec("EURUSD", "bullish", t))
    assert base != _key(_Rec("GBPUSD", "bullish", t))
    assert base != _key(_Rec("EURUSD", "bearish", t))
    assert base != _key(_Rec("EURUSD", "bullish", other))
    assert base == _key(_Rec("EURUSD", "bullish", t))


def test_fmt_price_handles_a_missing_value():
    assert _fmt_price(None) == "-"
    assert _fmt_price(1.35050) == "1.35050"


def test_variants_puts_the_baseline_first_and_one_entry_per_cap():
    from ..compare_liquidity_modes import variants
    v = variants([1, 3, 6])
    assert [name for name, _ in v] == ["swing", "single_candle/1",
                                       "single_candle/3", "single_candle/6"]
    assert v[0][1] == {"liquidity_mode": "swing"}
    assert v[2][1] == {"liquidity_mode": "single_candle", "single_candle_max_pools": 3}


def test_variants_with_no_caps_is_just_the_baseline():
    from ..compare_liquidity_modes import variants
    assert [name for name, _ in variants([])] == ["swing"]


def test_baseline_variant_never_carries_a_pool_cap():
    """swing must stay the untouched pre-2026-09-16 path -- passing it a
    single_candle-only knob would quietly make the baseline something
    else, and every number would be measured against the wrong thing."""
    from ..compare_liquidity_modes import variants
    for name, kwargs in variants([1, 2, 6]):
        if name == "swing":
            assert "single_candle_max_pools" not in kwargs
