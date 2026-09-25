"""
Key levels: the four shapes, and what a close through one does.
"""

from __future__ import annotations

import pandas as pd

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..levels import (broke_back, disrespected_by, flip, levels_confirmed_by,
                      returned_to, KeyLevel)

T0 = pd.Timestamp("2026-01-01")


def c(i, lo, hi, close=None):
    mid = (lo + hi) / 2
    return Candle(time=T0 + pd.Timedelta(hours=i), open=mid, high=hi, low=lo,
                  close=close if close is not None else mid, volume=0)


def test_a_swing_low_is_a_V_used_for_buys_and_a_swing_high_is_an_A():
    """bias-1 t=60-180."""
    bars = [c(0, 1.10, 1.12), c(1, 1.09, 1.11), c(2, 1.05, 1.07),   # the low
            c(3, 1.08, 1.10), c(4, 1.11, 1.13),
            c(5, 1.14, 1.20), c(6, 1.13, 1.16), c(7, 1.12, 1.15)]
    got = levels_confirmed_by(bars, n=2)

    v = [l for l in got if l.shape == "V"]
    a = [l for l in got if l.shape == "A"]
    assert v and v[0].price == 1.05 and v[0].bias == Direction.BULLISH
    assert a and a[0].price == 1.20 and a[0].bias == Direction.BEARISH


def test_the_last_n_candles_cannot_produce_a_level():
    """A swing at i is not a swing until i+n bars exist. This is the
    no-future guarantee, and it is arithmetic rather than a filter that
    has to remember itself."""
    bars = [c(0, 1.10, 1.12), c(1, 1.09, 1.11), c(2, 1.05, 1.07),
            c(3, 1.08, 1.10), c(4, 1.11, 1.13)]
    got = levels_confirmed_by(bars, n=2)
    assert [l.time for l in got] == [T0 + pd.Timedelta(hours=2)]

    # Truncate before that swing confirms and it does not exist at all.
    assert levels_confirmed_by(bars[:4], n=2) == []


def test_a_wick_through_does_not_disrespect_a_level():
    """"the moment [price] can CLOSE above this guy" -- a close, every
    time. A level that was merely tested is still the level it was."""
    sell_level = KeyLevel(T0, 1.1000, "A", Direction.BEARISH)

    wick = c(1, 1.0980, 1.1020, close=1.0990)
    body = c(1, 1.0980, 1.1020, close=1.1010)

    assert disrespected_by(wick, sell_level) is False
    assert disrespected_by(body, sell_level) is True


def test_a_disrespected_sell_level_becomes_a_buy_level_at_the_same_price():
    """"This was supposed to be used for sales -- that's when we now use
    it for a buy." The price does not move."""
    sell_level = KeyLevel(T0, 1.1000, "A", Direction.BEARISH)
    now = flip(sell_level)

    assert now.price == 1.1000, "the level is the same price"
    assert now.bias == Direction.BULLISH
    assert now.flipped is True
    assert now.shape == "A", "it is still the shape it was"


def test_the_return_may_overshoot_the_level():
    """Operator, 2026-09-22: "It can still come to the flip level too
    OR EVEN BELOW." Requiring the candle to straddle the level throws
    away every return that pokes through it."""
    buy_level = KeyLevel(T0, 1.1000, "A", Direction.BULLISH, flipped=True)

    exact = c(1, 1.1000, 1.1030)
    through = c(1, 1.0960, 1.1030)
    short_of_it = c(1, 1.1010, 1.1040)

    assert returned_to(exact, buy_level) is True
    assert returned_to(through, buy_level) is True, "overshooting still counts"
    assert returned_to(short_of_it, buy_level) is False


def test_a_breakout_back_the_other_way_invalidates_the_flip():
    """"but it must not create a breakout back to the opposite
    direction" -- a BODY close beyond a swing that formed AFTER the
    flip."""
    bars = [c(0, 1.10, 1.12), c(1, 1.09, 1.11),
            c(2, 1.10, 1.12, close=1.115),     # the flip happens here
            c(3, 1.11, 1.13), c(4, 1.12, 1.14),
            c(5, 1.08, 1.10), c(6, 1.09, 1.11),  # a swing low forms after
            c(7, 1.10, 1.12), c(8, 1.05, 1.09, close=1.06)]  # closes below it

    assert broke_back(bars, flip_idx=2, now_idx=8,
                      direction=Direction.BULLISH, n=2) is True


def test_a_close_beyond_a_swing_that_predates_the_flip_is_not_invalidation():
    """"a close beyond a swing that predates the flip is just price
    retracing into the level, which is the setup rather than its end.\""""
    bars = [c(0, 1.08, 1.10), c(1, 1.07, 1.09),
            c(2, 1.04, 1.06),                    # swing low BEFORE the flip
            c(3, 1.07, 1.09), c(4, 1.10, 1.12),
            c(5, 1.11, 1.13, close=1.125),       # flip here
            c(6, 1.09, 1.11), c(7, 1.05, 1.08, close=1.055)]  # below the old low

    assert broke_back(bars, flip_idx=5, now_idx=7,
                      direction=Direction.BULLISH, n=2) is False


def test_nothing_can_have_broken_back_before_the_flip():
    bars = [c(i, 1.10, 1.12) for i in range(6)]
    assert broke_back(bars, flip_idx=4, now_idx=3,
                      direction=Direction.BULLISH) is False
