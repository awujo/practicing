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
    v = variants([1, 3])
    assert [name for name, _ in v] == ["swing", "single_candle/1", "single_candle/3",
                                       "sc_h4/1", "sc_h4/3", "both/1", "both/3"]
    unbounded = variants([None])
    assert [name for name, _ in unbounded] == ["swing", "single_candle/all",
                                                "sc_h4/all", "both/all"]
    # "both" unions the two pool sources -- see runner's liquidity_mode
    # docstring and the 04:30-05:45 quote behind it.
    assert unbounded[3][1] == {"liquidity_mode": "both", "single_candle_max_pools": None}
    assert unbounded[1][1]["single_candle_max_pools"] is None
    assert v[0][1] == {"liquidity_mode": "swing"}
    assert v[2][1] == {"liquidity_mode": "single_candle", "single_candle_max_pools": 3}
    assert v[4][1] == {"liquidity_mode": "single_candle_h4", "single_candle_max_pools": 3}


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


def test_defaults_match_the_deployed_launch_flags():
    """Same guard as count_signals'. These already agreed with the
    deployment, but by two lists happening to match rather than by
    construction -- which is exactly the setup behind review findings 2
    and 8, where a gate and a test each validated a configuration nobody
    ran."""
    import argparse
    import sys
    from unittest import mock
    from ..live_flags import LIVE_FIXED_FLAGS, LIVE_LAUNCH_FLAGS
    from ..compare_liquidity_modes import main

    parsed = {}
    real = argparse.ArgumentParser.parse_args

    def capture(self, *a, **k):
        parsed.update(vars(real(self, *a, **k)))
        raise SystemExit(0)

    argv = ["compare_liquidity_modes", "--instruments", "NONE_AT_ALL"]
    with mock.patch.object(argparse.ArgumentParser, "parse_args", capture), \
            mock.patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit):
            main()

    assert parsed["origin_kind"] == LIVE_LAUNCH_FLAGS["origin_kind"]
    assert parsed["stop_anchor"] == LIVE_LAUNCH_FLAGS["stop_anchor"]
    assert parsed["min_reward_r"] == LIVE_FIXED_FLAGS["min_reward_r"]
    # Both of these are INVERTED flags: absent means the behaviour is ON,
    # which is what the bots run. Asserted as plain `is False` -- the
    # first version of this line read `not x is False or True`, which is
    # a tautology and would have passed on any value at all.
    assert parsed["wick_based_sweep_break"] is False   # -> close-based ON
    assert parsed["no_avoid_rollover"] is False        # -> rollover avoidance ON
    assert LIVE_FIXED_FLAGS["avoid_rollover_entries"] is True
