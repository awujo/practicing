"""
Three conditions, one rule. Rejection, closure, lower-timeframe break.
"""

from __future__ import annotations

import pandas as pd

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..bias import bias_established, breakout_after, rejected_at
from ..levels import KeyLevel

T0 = pd.Timestamp("2026-01-01")


def c(i, lo, hi, close, step="h"):
    mid = (lo + hi) / 2
    return Candle(time=T0 + pd.Timedelta(**{f"{step}ours" if step == "h" else "days": i}),
                  open=mid, high=hi, low=lo, close=close, volume=0)


def test_a_tap_without_a_closure_is_only_a_test():
    """Conditions 1 and 2 are one event. "How price [taps] into that
    particular key level AND number two, how price CLOSES below"."""
    sell_level = KeyLevel(T0, 1.1000, "A", Direction.BEARISH)

    tapped_and_closed_below = c(1, 1.0950, 1.1010, 1.0960)
    tapped_and_closed_above = c(1, 1.0950, 1.1010, 1.1005)
    never_reached_it = c(1, 1.0900, 1.0980, 1.0950)

    assert rejected_at(tapped_and_closed_below, sell_level) is True
    assert rejected_at(tapped_and_closed_above, sell_level) is False, "still a test"
    assert rejected_at(never_reached_it, sell_level) is False, "price passed by"


def test_the_buy_case_is_mirrored():
    buy_level = KeyLevel(T0, 1.1000, "V", Direction.BULLISH)
    assert rejected_at(c(1, 1.0990, 1.1050, 1.1040), buy_level) is True
    assert rejected_at(c(1, 1.0990, 1.1050, 1.0995), buy_level) is False


def test_a_wick_beyond_a_swing_is_not_a_breakout():
    """A BODY close, the same reading of "breakout" used everywhere
    else in the course."""
    bars = [c(0, 1.10, 1.12, 1.11), c(1, 1.09, 1.11, 1.10),
            c(2, 1.13, 1.16, 1.15),      # swing high 1.16
            c(3, 1.11, 1.13, 1.12), c(4, 1.10, 1.12, 1.11),
            c(5, 1.12, 1.17, 1.13)]      # wicks past 1.16, closes under
    assert breakout_after(bars, 0, Direction.BULLISH, n=2) is False

    bars[5] = c(5, 1.12, 1.18, 1.17)     # now closes beyond
    assert breakout_after(bars, 0, Direction.BULLISH, n=2) is True


def test_a_swing_that_predates_the_rejection_does_not_count():
    """"A close beyond one that predates the rejection says nothing
    about what the rejection started.\""""
    bars = [c(0, 1.13, 1.16, 1.15),      # swing high, before the rejection
            c(1, 1.11, 1.13, 1.12), c(2, 1.10, 1.12, 1.11),
            c(3, 1.11, 1.13, 1.12), c(4, 1.12, 1.18, 1.17)]   # closes past it
    # Rejection happens at index 3, after that swing already existed.
    assert breakout_after(bars, 3, Direction.BULLISH, n=2) is False


def test_no_lower_timeframe_break_means_no_bias():
    """Condition 3 is something price must DO. The absence of a
    contrary signal is not a bias -- which is how the old cascade could
    flip on an empty window."""
    level = KeyLevel(T0, 1.1000, "A", Direction.BEARISH)
    higher = [c(0, 1.0950, 1.1010, 1.0960, step="d")]     # rejection
    quiet = [c(i, 1.0950, 1.0970, 1.0960) for i in range(12)]

    assert bias_established(higher, quiet, level) is None


def test_all_three_conditions_give_a_bias():
    level = KeyLevel(T0, 1.1000, "A", Direction.BEARISH)
    higher = [c(0, 1.0950, 1.1010, 1.0960, step="d")]

    lower = [c(0, 1.0950, 1.0970, 1.0960), c(1, 1.0955, 1.0975, 1.0965),
             c(2, 1.0930, 1.0950, 1.0940),    # swing LOW 1.0930
             c(3, 1.0945, 1.0965, 1.0955), c(4, 1.0950, 1.0970, 1.0960),
             c(5, 1.0900, 1.0940, 1.0910)]    # closes below the swing low
    assert bias_established(higher, lower, level) == Direction.BEARISH


def test_a_rejection_that_never_happened_gives_no_bias():
    level = KeyLevel(T0, 1.1000, "A", Direction.BEARISH)
    higher = [c(0, 1.0900, 1.0950, 1.0920, step="d")]     # never reached it
    lower = [c(i, 1.0900, 1.0920, 1.0910) for i in range(8)]
    assert bias_established(higher, lower, level) is None
