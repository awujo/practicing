"""
The L in SLK: which extreme is internal, when it is taken, and which key
level that entitles you to trade.
"""

from __future__ import annotations

import pandas as pd

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..levels import KeyLevel
from ..sweep import (LiquidityPoint, LiquidityStream, SetupStream,
                     external_kind, internal_kind, nearest_level, role_of)

T0 = pd.Timestamp("2026-01-01")


def h4(i, o, h, l, c):
    return Candle(time=T0 + pd.Timedelta(hours=4 * i), open=o, high=h, low=l,
                  close=c, volume=0)


def v(price, i=0):
    """A V-shape (buy) key level."""
    return KeyLevel(T0 + pd.Timedelta(hours=4 * i), price, "V",
                    Direction.BULLISH)


def a(price, i=0):
    """An A-shape (sell) key level."""
    return KeyLevel(T0 + pd.Timedelta(hours=4 * i), price, "A",
                    Direction.BEARISH)


# --- which extreme is which -------------------------------------------

def test_the_internal_extreme_depends_on_the_formation():
    """video-18 t=321-331: "if it is a bullish formation this LOW is
    going to be the internal range, the HIGH is going to be the external
    range; if it's a bearish formation this HIGH is going to be the
    internal range, this LOW is going to be the external range"."""
    assert internal_kind(Direction.BULLISH) == "low"
    assert external_kind(Direction.BULLISH) == "high"
    assert internal_kind(Direction.BEARISH) == "high"
    assert external_kind(Direction.BEARISH) == "low"

    assert role_of("low", Direction.BULLISH) == "internal"
    assert role_of("low", Direction.BEARISH) == "external"


# --- resting liquidity, taken as it is taken ---------------------------

def test_a_candle_cannot_take_its_own_liquidity():
    """Its extremes are registered after it has been used to consume, so
    the first candle in a series takes nothing."""
    s = LiquidityStream()
    assert s.push(h4(0, 1.10, 1.15, 1.05, 1.12)) == []
    assert len(s) == 2, "its own high and low now rest"


def test_the_next_candle_taking_a_low_is_the_sweep():
    """repeating-system t=164-178: "the low of this candle is swept by
    this particular one right here"."""
    s = LiquidityStream()
    s.push(h4(0, 1.10, 1.15, 1.05, 1.12))
    taken = s.push(h4(1, 1.12, 1.14, 1.04, 1.13))

    prices = sorted(sw.point.price for sw in taken)
    assert prices == [1.05], "the 1.05 low went; the 1.15 high did not"


def test_liquidity_need_not_be_the_immediate_candle():
    """repeating-system t=285-296: "not always the immediate candle. You
    can also have another candle to the upside at this particular
    level"."""
    s = LiquidityStream()
    s.push(h4(0, 1.10, 1.15, 1.05, 1.12))      # low 1.05
    s.push(h4(1, 1.12, 1.13, 1.08, 1.09))      # low 1.08, takes nothing
    s.push(h4(2, 1.09, 1.11, 1.09, 1.10))      # takes nothing
    taken = s.push(h4(3, 1.10, 1.10, 1.04, 1.05))

    prices = sorted(sw.point.price for sw in taken)
    assert 1.05 in prices, "the low from three candles ago was still resting"
    assert 1.08 in prices, "so was the nearer one -- both went at once"


def test_a_taken_point_is_taken_once():
    """Otherwise every subsequent candle re-reports the same sweep and
    anything counting setups counts one event many times."""
    s = LiquidityStream()
    s.push(h4(0, 1.10, 1.15, 1.05, 1.12))
    s.push(h4(1, 1.12, 1.14, 1.04, 1.13))      # takes 1.05
    taken = s.push(h4(2, 1.13, 1.135, 1.03, 1.04))

    assert 1.05 not in [sw.point.price for sw in taken], "already gone"
    assert 1.04 in [sw.point.price for sw in taken], "this one is new"


def test_taken_is_a_trade_through_not_a_close_through():
    """video-18 t=390-404 lets the SAME candle take a high then go for
    the low; one candle cannot close back on both sides, so the
    definition has to be the trade through."""
    s = LiquidityStream()
    s.push(h4(0, 1.10, 1.15, 1.05, 1.12))
    taken = s.push(h4(1, 1.12, 1.16, 1.04, 1.12))   # wicks both ways, closes inside

    prices = sorted(sw.point.price for sw in taken)
    assert prices == [1.05, 1.15], "both extremes taken by wicks alone"


# --- the nearest key level --------------------------------------------

def test_the_eligible_level_is_the_nearest_to_the_taken_liquidity():
    """video-18 t=481-489: "price will look for the nearest liquidity,
    that is the nearest key level that this low is resting close to"."""
    point = LiquidityPoint(T0, 1.0500, "low")
    levels = [v(1.0300), v(1.0490), v(1.0800)]
    assert nearest_level(point, levels, Direction.BULLISH).price == 1.0490


def test_a_level_in_the_wrong_direction_is_not_a_candidate():
    """A buy is taken from a level currently used for buys."""
    point = LiquidityPoint(T0, 1.0500, "low")
    levels = [a(1.0499), v(1.0700)]
    assert nearest_level(point, levels, Direction.BULLISH).price == 1.0700
    assert nearest_level(point, levels, Direction.BEARISH).price == 1.0499


def test_no_level_yet_is_none_rather_than_a_guess():
    assert nearest_level(LiquidityPoint(T0, 1.05, "low"), [],
                         Direction.BULLISH) is None


# --- the three steps together -----------------------------------------

def test_a_level_price_reached_without_taking_liquidity_is_no_setup():
    """This is the whole point of the module. The old engine entered
    because price touched a level; t=465-481 is Bishop refusing exactly
    that: "the reason why you're NOT going to take this V-shaped key
    level ... is because you can actually pay attention to the story"."""
    s = SetupStream()
    level = v(1.0500)

    # The first candle rests liquidity and takes none. It reaches the
    # level and closes back above it -- a textbook rejection -- but no
    # internal range liquidity has been taken, so there is no setup.
    got = s.push(h4(0, 1.0600, 1.0620, 1.0490, 1.0580), Direction.BULLISH,
                 [level])
    assert got == [], "rejection without a sweep is not an SLK setup"


def test_liquidity_taken_then_the_level_rejects_is_the_setup():
    """The sequence in full: repeating-system t=111-139."""
    s = SetupStream()
    level = v(1.0500)

    s.push(h4(0, 1.0600, 1.0620, 1.0550, 1.0580), Direction.BULLISH, [level])
    # takes the 1.0550 low (internal, bullish) and rejects off 1.0500
    got = s.push(h4(1, 1.0570, 1.0575, 1.0495, 1.0560), Direction.BULLISH,
                 [level])

    assert len(got) == 1
    setup = got[0]
    assert setup.level.price == 1.0500
    assert setup.sweep.point.price == 1.0550
    assert setup.sweep.role == "internal"
    assert setup.same_candle, "one candle both took the low and rejected"


def test_the_sweep_arms_the_setup_and_a_later_candle_rejects():
    """t=386-395: "we want to see price after taking that particular
    high, we want to see the next candle that is going to form take out
    our low" -- the steps may land on different candles."""
    s = SetupStream()
    level = v(1.0500)

    s.push(h4(0, 1.0600, 1.0620, 1.0550, 1.0580), Direction.BULLISH, [level])
    # takes the low, but does not reach the level
    assert s.push(h4(1, 1.0570, 1.0575, 1.0540, 1.0545), Direction.BULLISH,
                  [level]) == []
    assert len(s) == 1, "armed, waiting on the level"
    # now the level rejects
    got = s.push(h4(2, 1.0545, 1.0550, 1.0498, 1.0530), Direction.BULLISH,
                 [level])
    assert len(got) == 1
    assert not got[0].same_candle


def test_taking_external_liquidity_arms_nothing():
    """t=418-446: external range liquidity taken leads to a
    RETRACEMENT, so a bullish bias may not buy on a high being taken --
    it has to wait for the low."""
    s = SetupStream()
    level = v(1.0500)

    s.push(h4(0, 1.0600, 1.0620, 1.0550, 1.0580), Direction.BULLISH, [level])
    # takes the 1.0620 HIGH -- external under a bullish bias
    got = s.push(h4(1, 1.0580, 1.0650, 1.0570, 1.0640), Direction.BULLISH,
                 [level])
    assert got == [], "a high taken is a retracement due, not a buy"
    assert len(s) == 0, "and nothing is armed by it"


def test_a_level_closed_through_stops_being_the_setup():
    """levels.py: a level lasts "until they get disrespected", and a
    close through is what does it."""
    s = SetupStream()
    level = v(1.0500)

    s.push(h4(0, 1.0600, 1.0620, 1.0550, 1.0580), Direction.BULLISH, [level])
    got = s.push(h4(1, 1.0570, 1.0575, 1.0480, 1.0485), Direction.BULLISH,
                 [level])
    assert got == [], "it closed below the level -- that is a disrespect"
    assert len(s) == 0


def test_no_bias_means_no_internal_range_and_no_setups():
    """Which extreme is internal is a function of the formation. Without
    one the question has no answer -- and liquidity still accrues."""
    s = SetupStream()
    assert s.push(h4(0, 1.0600, 1.0620, 1.0550, 1.0580), None, [v(1.05)]) == []
    assert s.push(h4(1, 1.0570, 1.0575, 1.0495, 1.0560), None, [v(1.05)]) == []
    # the low was still registered, so a bias arriving now can use it
    got = s.push(h4(2, 1.0560, 1.0565, 1.0490, 1.0550), Direction.BULLISH,
                 [v(1.0500)])
    assert len(got) == 1, "the earlier lows were resting all along"


def test_a_bias_flip_drops_setups_armed_under_the_old_read():
    """video-03 t=1892-1914: the order went because the analysis went.
    A setup armed under the old bias is the same thing one step
    earlier."""
    s = SetupStream()
    s.push(h4(0, 1.0600, 1.0620, 1.0550, 1.0580), Direction.BULLISH, [v(1.05)])
    s.push(h4(1, 1.0570, 1.0575, 1.0540, 1.0545), Direction.BULLISH, [v(1.05)])
    assert len(s) == 1

    got = s.push(h4(2, 1.0545, 1.0560, 1.0542, 1.0550), Direction.BEARISH,
                 [a(1.0560)])
    assert len(s) == 0, "the bullish pending is gone"
    assert got == [], "and it did not fire as a bearish setup either"


def test_a_string_of_lower_lows_into_one_level_is_one_setup():
    """A retracement takes a new low every candle, and every one of them
    has the same key level as its nearest. Keying on the sweep fired the
    same setup several times on one candle -- the same overtrading that
    put three orders three pips apart on one H1 bar."""
    s = SetupStream()
    level = v(1.0500)
    bars = [h4(0, 1.0600, 1.0620, 1.0590, 1.0595),
            h4(1, 1.0595, 1.0600, 1.0580, 1.0585),
            h4(2, 1.0585, 1.0590, 1.0570, 1.0575),
            h4(3, 1.0575, 1.0580, 1.0560, 1.0565)]
    fired = []
    for bar in bars:
        fired += s.push(bar, Direction.BULLISH, [level])
    assert fired == [], "the level has not been reached yet"
    assert len(s) == 1, "four sweeps, one level, one pending setup"

    got = s.push(h4(4, 1.0565, 1.0570, 1.0495, 1.0540), Direction.BULLISH,
                 [level])
    assert len(got) == 1, "and it fires exactly once"


def test_a_level_once_closed_through_does_not_arm_again():
    """A level lasts "until they get disrespected". After that it is a
    flip level for the other side -- which this package models in
    levels.flip but the level stream does not yet feed back, so here it
    simply stops being a buy level."""
    s = SetupStream()
    level = v(1.0500)

    s.push(h4(0, 1.0600, 1.0620, 1.0550, 1.0580), Direction.BULLISH, [level])
    s.push(h4(1, 1.0570, 1.0575, 1.0480, 1.0485), Direction.BULLISH, [level])
    assert len(s) == 0, "disrespected"

    # price comes back up, then sweeps down into it again
    s.push(h4(2, 1.0485, 1.0600, 1.0480, 1.0590), Direction.BULLISH, [level])
    got = s.push(h4(3, 1.0590, 1.0595, 1.0495, 1.0560), Direction.BULLISH,
                 [level])
    assert got == [], "it is not a buy level any more"


def test_the_bearish_mirror():
    """The high is internal under a bearish bias, so a high taken is
    what entitles a sell."""
    s = SetupStream()
    level = a(1.0700)

    s.push(h4(0, 1.0600, 1.0650, 1.0580, 1.0620), Direction.BEARISH, [level])
    # takes the 1.0650 high (internal, bearish) and rejects off 1.0700
    got = s.push(h4(1, 1.0620, 1.0705, 1.0615, 1.0660), Direction.BEARISH,
                 [level])

    assert len(got) == 1
    assert got[0].sweep.point.price == 1.0650
    assert got[0].level.price == 1.0700


# --- bias from liquidity, Bishop's own checklist -----------------------

from ..sweep import LiquidityBias           # noqa: E402
from ..sweep import bias_from_internal      # noqa: E402


def wk(i, o, h, l, c):
    return Candle(time=T0 + pd.Timedelta(days=7 * i), open=o, high=h, low=l,
                  close=c, volume=0)


def wk_close(i):
    return T0 + pd.Timedelta(days=7 * (i + 1))


def dly(i, o, h, l, c):
    return Candle(time=T0 + pd.Timedelta(days=i), open=o, high=h, low=l,
                  close=c, volume=0)


def test_a_sweep_direction_is_the_formation_it_is_internal_to():
    assert bias_from_internal("low") == Direction.BULLISH
    assert bias_from_internal("high") == Direction.BEARISH


def test_a_previous_weekly_low_swept_with_the_high_standing_is_bullish():
    """daily-routine t=534-540: "I have my checklist: previous daily
    weekly low sweep, what's daily breakout to the upside"."""
    b = LiquidityBias()
    b.push(wk(0, 1.10, 1.20, 1.05, 1.15), wk_close(0))
    assert b.latest is None, "a candle cannot sweep its own low"

    b.push(wk(1, 1.15, 1.18, 1.04, 1.12), wk_close(1))
    assert b.latest is not None
    assert b.latest[0] == Direction.BULLISH, "the low went, the 1.20 stands"


def test_a_previous_weekly_high_swept_with_a_low_standing_is_bearish():
    """t=1012-1024, his words exactly: "previous weekly high sweep with a
    low standing"."""
    b = LiquidityBias()
    b.push(wk(0, 1.10, 1.20, 1.05, 1.15), wk_close(0))
    b.push(wk(1, 1.15, 1.22, 1.14, 1.16), wk_close(1))
    assert b.latest[0] == Direction.BEARISH


def test_taking_both_sides_of_one_period_leaves_no_story():
    """The single candle formation is a high AND a low. Once both are
    gone there is no expansion left to expect from it."""
    b = LiquidityBias()
    b.push(wk(0, 1.10, 1.20, 1.05, 1.15), wk_close(0))
    b.push(wk(1, 1.15, 1.25, 1.02, 1.10), wk_close(1))
    assert b.latest is None, "engulfed both extremes -- neither side stands"


def test_the_checklist_needs_the_lower_timeframe_to_break_too():
    """Item two is something price must DO, exactly like condition 3 of
    the key-level route. A sweep on its own is not a bias."""
    b = LiquidityBias()
    b.push(wk(0, 1.10, 1.20, 1.05, 1.15), wk_close(0))
    b.push(wk(1, 1.15, 1.18, 1.04, 1.12), wk_close(1))

    quiet = [dly(14 + i, 1.12, 1.125, 1.115, 1.12) for i in range(12)]
    assert b.direction(quiet, n=2) is None, "no daily breakout, no bias"


def test_a_daily_break_before_the_sweep_does_not_count():
    """A weekly candle says a low went that week, not on which day. A
    daily break inside the same week could precede the sweep it is meant
    to confirm, so only days after the week's CLOSE are eligible."""
    b = LiquidityBias()
    b.push(wk(0, 1.10, 1.20, 1.05, 1.15), wk_close(0))
    b.push(wk(1, 1.15, 1.18, 1.04, 1.12), wk_close(1))

    # The SAME days that do establish the bias in the test below, moved
    # back inside week 1. Using the identical shape is the point: it is a
    # control, and without it this test would pass on a fixture that
    # simply has no breakout in it -- which is how the first version of
    # it passed while proving nothing.
    inside = [dly(7, 1.12, 1.13, 1.11, 1.12),
              dly(8, 1.12, 1.14, 1.115, 1.13),
              dly(9, 1.13, 1.16, 1.125, 1.15),
              dly(10, 1.15, 1.155, 1.14, 1.145),
              dly(11, 1.145, 1.15, 1.135, 1.14),
              dly(12, 1.14, 1.18, 1.138, 1.17)]
    after = [dly(14 + i, c.open, c.high, c.low, c.close)
             for i, c in enumerate(inside)]

    assert b.direction(after, n=2) == Direction.BULLISH, \
        "the control: after the close, this shape is a bias"
    assert b.direction(inside, n=2) is None, \
        "the same shape before the close is not"


def test_the_full_checklist_establishes_the_bias():
    b = LiquidityBias()
    b.push(wk(0, 1.10, 1.20, 1.05, 1.15), wk_close(0))
    b.push(wk(1, 1.15, 1.18, 1.04, 1.12), wk_close(1))

    # week 1 closed on day 14, so these are all eligible. An A-shape
    # swing forms at 1.16 and a later day closes above it.
    days = [dly(14, 1.12, 1.13, 1.11, 1.12),
            dly(15, 1.12, 1.14, 1.115, 1.13),
            dly(16, 1.13, 1.16, 1.125, 1.15),     # the swing high
            dly(17, 1.15, 1.155, 1.14, 1.145),
            dly(18, 1.145, 1.15, 1.135, 1.14),
            dly(19, 1.14, 1.18, 1.138, 1.17)]     # closes above 1.16
    assert b.direction(days, n=2) == Direction.BULLISH
