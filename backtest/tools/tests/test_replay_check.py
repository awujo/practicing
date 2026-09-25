"""
The cutter must actually cut, and it must cut on the CLOSE.

Written because the first version of `_truncating_loader` filtered on
each candle's OPEN, which admitted a Daily bar that had started but not
finished -- handing the engine that whole day's final high and low,
including the part that had not happened. A cutter with a leak in it is
worse than none, because it certifies.
"""

from __future__ import annotations

import pandas as pd

from ...engine.candles import Candle
from ..replay_check import _truncating_loader


def _daily(n):
    base = pd.Timestamp("2026-01-01")
    return [Candle(time=base + pd.Timedelta(days=i), open=1.0, high=2.0,
                   low=0.5, close=1.5, volume=0) for i in range(n)]


def _hourly(n):
    base = pd.Timestamp("2026-01-01")
    return [Candle(time=base + pd.Timedelta(hours=i), open=1.0, high=1.1,
                   low=0.9, close=1.05, volume=0) for i in range(n)]


def test_a_period_that_has_not_closed_is_not_on_the_chart():
    """Cutting midway through 2026-01-03 must not show that day's bar.

    Its cached high and low are the day's FINAL values, so admitting it
    leaks the rest of the session -- which is precisely the look-ahead
    this tool was built to detect."""
    daily = _daily(10)
    cutoff = pd.Timestamp("2026-01-03 15:00")
    load = _truncating_loader(lambda s, y, g: daily, cutoff)
    got = load("dukascopy", "EURUSD", "D")

    assert [c.time for c in got] == [
        pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")]
    assert pd.Timestamp("2026-01-03") not in [c.time for c in got], \
        "the still-forming day must not be visible"


def test_the_candle_that_closes_exactly_at_the_cutoff_is_included():
    """The decision is made on a close, so that close must be on the
    chart -- cutting it would hide the candle the trigger fired on."""
    hourly = _hourly(24)
    cutoff = pd.Timestamp("2026-01-01 05:00")   # the 04:00 bar closes here
    load = _truncating_loader(lambda s, y, g: hourly, cutoff)
    got = load("dukascopy", "EURUSD", "H1")

    assert got[-1].time == pd.Timestamp("2026-01-01 04:00")


def test_the_cutter_is_applied_to_every_series_independently():
    """Daily and H1 close at different times; each must be cut by its
    own bar length, not by a single shared assumption."""
    cutoff = pd.Timestamp("2026-01-03 15:00")
    series = {"D": _daily(10), "H1": _hourly(24 * 10)}
    load = _truncating_loader(lambda s, y, g: series[g], cutoff)

    assert load("x", "y", "D")[-1].time == pd.Timestamp("2026-01-02")
    assert load("x", "y", "H1")[-1].time == pd.Timestamp("2026-01-03 14:00")


def test_an_empty_series_does_not_blow_up():
    load = _truncating_loader(lambda s, y, g: [], pd.Timestamp("2026-01-03"))
    assert load("x", "y", "D") == []
