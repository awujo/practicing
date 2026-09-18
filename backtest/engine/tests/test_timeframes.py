"""Tests for bar-length inference.

This is load-bearing: every `known_at` in the engine is now built on it,
so an inference that is wrong in the optimistic direction silently
restores the look-ahead the 2026-09-18 review found. The cases below are
the ones real series actually produce.
"""

import pandas as pd
import pytest

from ..candles import Candle
from ..timeframes import bar_length, closes_at, infer_bar_length


def _series(times):
    return [Candle(time=pd.Timestamp(t, tz="UTC"), open=1.0, high=1.0,
                   low=1.0, close=1.0, volume=1.0) for t in times]


def test_h4_series():
    c = _series(["2026-09-17 00:00", "2026-09-17 04:00", "2026-09-17 08:00"])
    assert infer_bar_length(c) == pd.Timedelta(hours=4)


def test_weekend_gap_does_not_outvote_the_real_daily_length():
    """A Daily series skips Saturday and Sunday, so one gap in five is
    three days. The modal gap must still be one day -- every real gap is
    LONGER than the bar, never shorter, which is what makes the mode
    safe here."""
    c = _series(["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17",
                 "2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23"])
    assert infer_bar_length(c) == pd.Timedelta(days=1)


def test_weekly_series():
    c = _series(["2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21"])
    assert infer_bar_length(c) == pd.Timedelta(days=7)


def test_a_long_feed_outage_does_not_change_the_answer():
    c = _series(["2026-09-17 00:00", "2026-09-17 01:00", "2026-09-17 02:00",
                 "2026-09-19 12:00", "2026-09-19 13:00", "2026-09-19 14:00"])
    assert infer_bar_length(c) == pd.Timedelta(hours=1)


def test_too_short_to_tell_returns_none_rather_than_guessing():
    assert infer_bar_length([]) is None
    assert infer_bar_length(_series(["2026-09-17"])) is None


def test_duplicate_timestamps_are_ignored_not_counted_as_zero():
    """A zero gap would otherwise win the mode outright and make every
    bar knowable at its own open -- the exact bug being fixed."""
    c = _series(["2026-09-17 00:00", "2026-09-17 00:00", "2026-09-17 04:00",
                 "2026-09-17 08:00"])
    assert infer_bar_length(c) == pd.Timedelta(hours=4)


def test_named_fallback_only_applies_when_the_data_cannot_say():
    one = _series(["2026-09-17"])
    assert bar_length(one, "H4") == pd.Timedelta(hours=4)
    # Data wins over a label that disagrees with it -- the label is a
    # human assertion, the spacing is the evidence.
    h4 = _series(["2026-09-17 00:00", "2026-09-17 04:00", "2026-09-17 08:00"])
    assert bar_length(h4, "D") == pd.Timedelta(hours=4)


def test_no_length_available_degrades_to_the_bars_own_open():
    t = pd.Timestamp("2026-09-17 12:00", tz="UTC")
    assert closes_at(t, None) == t
    assert closes_at(t, pd.Timedelta(hours=4)) == pd.Timestamp("2026-09-17 16:00", tz="UTC")
