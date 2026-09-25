"""
The other confirmation forms: inducement, breakout, sweep and break.
"""

from __future__ import annotations

import pandas as pd

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..entries import (Confirmation, InducementWatch, ReactionWatch,
                       mitigation_price)
from ..levels import KeyLevel

T0 = pd.Timestamp("2026-01-01")


def h1(i, o, h, l, c):
    return Candle(time=T0 + pd.Timedelta(hours=i), open=o, high=h, low=l,
                  close=c, volume=0)


def v(price):
    return KeyLevel(T0, price, "V", Direction.BULLISH)


def a(price):
    return KeyLevel(T0, price, "A", Direction.BEARISH)


# --- the line-chart peak (5.1, measured not traded) --------------------

def test_the_line_chart_peak_is_the_last_close_before_the_turn():
    """video-14 t=505-512: move to the line chart and the engulf has
    "created for us another A shape". A line chart plots closes, so the
    peak is where the closes turned."""
    before = [h1(0, 1.10, 1.11, 1.09, 1.1000),
              h1(1, 1.10, 1.12, 1.10, 1.1050),
              h1(2, 1.105, 1.13, 1.104, 1.1080)]   # the peak
    assert mitigation_price(before, Direction.BEARISH) == 1.1080


def test_the_peak_stops_at_the_turn_rather_than_scanning_all_history():
    """A dip before the run up must not be crossed -- the A shape the
    engulf created is the one it created, not the highest close ever."""
    before = [h1(0, 1.10, 1.20, 1.09, 1.1900),     # higher, but before a turn
              h1(1, 1.19, 1.20, 1.10, 1.1000),
              h1(2, 1.10, 1.12, 1.10, 1.1050),
              h1(3, 1.105, 1.13, 1.104, 1.1080)]
    assert mitigation_price(before, Direction.BEARISH) == 1.1080, \
        "the 1.19 sits on the far side of a turn"


def test_the_bullish_peak_is_a_trough():
    before = [h1(0, 1.10, 1.11, 1.09, 1.1000),
              h1(1, 1.10, 1.105, 1.08, 1.0900),
              h1(2, 1.09, 1.095, 1.07, 1.0850)]
    assert mitigation_price(before, Direction.BULLISH) == 1.0850


def test_no_history_is_none_rather_than_a_guess():
    assert mitigation_price([], Direction.BEARISH) is None


# --- 5.3 inducement ----------------------------------------------------

def _run_inducement(bars, direction, level, engulf_at):
    w = InducementWatch()
    out = []
    for bar in bars:
        got = w.push(bar, direction, level)
        if got:
            out.append(got)
        if bar.time == engulf_at:
            w.engulfed(bar)
    return out


def test_the_candle_after_the_engulf_becomes_the_liquidity():
    """video-14 t=679-702, bearish: the next candle trades close to the A
    shape key level but does not tap it, so it IS the internal range
    liquidity. Price takes it, then plays the level."""
    level = a(1.1100)
    bars = [
        h1(0, 1.1050, 1.1060, 1.1040, 1.1045),   # settle the watch on the level
        h1(1, 1.1045, 1.1050, 1.1000, 1.1005),   # the engulf
        h1(2, 1.1005, 1.1090, 1.1000, 1.1080),   # candidate: 1.1090 < 1.1100
        h1(3, 1.1080, 1.1085, 1.1060, 1.1065),   # nothing
        h1(4, 1.1065, 1.1095, 1.1060, 1.1090),   # takes the 1.1090 liquidity
        h1(5, 1.1090, 1.1105, 1.1085, 1.1095),   # plays the level
    ]
    got = _run_inducement(bars, Direction.BEARISH, level,
                          engulf_at=bars[1].time)

    assert len(got) == 1
    assert got[0].form == "inducement"
    assert got[0].entry == 1.1100, "the entry is the key level itself"
    assert got[0].stop == 1.1105, "the far side of the candle that confirmed"


def test_a_candidate_that_taps_the_level_is_not_inducement():
    """"But it's NOT GOING TO TAP INTO IT" -- a candle that reaches the
    level is price playing the level, not liquidity resting below it."""
    level = a(1.1100)
    bars = [
        h1(0, 1.1050, 1.1060, 1.1040, 1.1045),
        h1(1, 1.1045, 1.1050, 1.1000, 1.1005),   # engulf
        h1(2, 1.1005, 1.1110, 1.1000, 1.1080),   # taps 1.1100
        h1(3, 1.1080, 1.1120, 1.1075, 1.1110),
    ]
    assert _run_inducement(bars, Direction.BEARISH, level,
                           engulf_at=bars[1].time) == []


def test_only_the_next_candle_is_the_candidate():
    """It is "the NEXT one hour or 30 minutes candle", not whichever
    later one happens to fall short. Without that the condition is just
    "a candle that did not reach the level", which is nearly all of
    them."""
    level = a(1.1100)
    bars = [
        h1(0, 1.1050, 1.1060, 1.1040, 1.1045),
        h1(1, 1.1045, 1.1050, 1.1000, 1.1005),   # engulf
        h1(2, 1.1005, 1.1110, 1.1000, 1.1080),   # candidate, and it TAPS
        h1(3, 1.1080, 1.1090, 1.1070, 1.1075),   # falls short, but too late
        h1(4, 1.1075, 1.1095, 1.1070, 1.1090),
        h1(5, 1.1090, 1.1105, 1.1085, 1.1095),
    ]
    assert _run_inducement(bars, Direction.BEARISH, level,
                           engulf_at=bars[1].time) == [], \
        "candle 3 is not the next candle"


def test_the_liquidity_must_be_taken_before_the_level_counts():
    """"We want to see price ATTACK THAT LIQUIDITY, play out from this
    particular key level" -- in that order."""
    level = a(1.1100)
    bars = [
        h1(0, 1.1050, 1.1060, 1.1040, 1.1045),
        h1(1, 1.1045, 1.1050, 1.1000, 1.1005),   # engulf
        h1(2, 1.1005, 1.1090, 1.1000, 1.1080),   # inducement at 1.1090
        h1(3, 1.1080, 1.1085, 1.1060, 1.1065),
        h1(4, 1.1065, 1.1080, 1.1060, 1.1070),
    ]
    assert _run_inducement(bars, Direction.BEARISH, level,
                           engulf_at=bars[1].time) == [], \
        "the 1.1090 was never taken"


def test_one_candle_may_take_the_liquidity_and_play_the_level():
    level = a(1.1100)
    bars = [
        h1(0, 1.1050, 1.1060, 1.1040, 1.1045),
        h1(1, 1.1045, 1.1050, 1.1000, 1.1005),   # engulf
        h1(2, 1.1005, 1.1090, 1.1000, 1.1080),   # inducement at 1.1090
        h1(3, 1.1080, 1.1108, 1.1075, 1.1085),   # takes it AND taps the level
    ]
    got = _run_inducement(bars, Direction.BEARISH, level,
                          engulf_at=bars[1].time)
    assert len(got) == 1
    assert got[0].stop == 1.1108


def test_the_bullish_mirror_of_inducement():
    level = v(1.0900)
    bars = [
        h1(0, 1.0950, 1.0960, 1.0940, 1.0955),
        h1(1, 1.0955, 1.1000, 1.0950, 1.0995),   # engulf up
        h1(2, 1.0995, 1.1000, 1.0910, 1.0920),   # candidate: 1.0910 > 1.0900
        h1(3, 1.0920, 1.0940, 1.0905, 1.0910),   # takes the 1.0910
        h1(4, 1.0910, 1.0915, 1.0895, 1.0900),   # plays the level
    ]
    got = _run_inducement(bars, Direction.BULLISH, level,
                          engulf_at=bars[1].time)
    assert len(got) == 1
    assert got[0].entry == 1.0900
    assert got[0].stop == 1.0895


# --- 5.4 / 5.5 the reaction breaking its own structure -----------------

def _run_reaction(bars, direction, level, n=2):
    w = ReactionWatch(n)
    return [c for c in (w.push(b, direction, level) for b in bars) if c]


def test_a_breakout_of_the_minor_swing_is_the_confirmation():
    """part5 t=376-401: price reacts at the level, lifts leaving a minor
    swing, and the break of THAT is the confirmation -- the spec measured
    the marked segment at 1.86789, above the 1.86700 key level, so the
    reference is the minor swing and not the level."""
    level = v(1.0900)
    bars = [
        h1(0, 1.0905, 1.0910, 1.0898, 1.0902),   # in at the level
        h1(1, 1.0902, 1.0915, 1.0900, 1.0912),
        h1(2, 1.0912, 1.0930, 1.0910, 1.0928),   # the minor swing high
        h1(3, 1.0928, 1.0929, 1.0915, 1.0918),
        h1(4, 1.0918, 1.0920, 1.0910, 1.0914),   # confirms the swing at n=2
        h1(5, 1.0914, 1.0935, 1.0912, 1.0932),   # closes through 1.0930
    ]
    got = _run_reaction(bars, Direction.BULLISH, level)

    assert len(got) == 1
    assert got[0].form == "breakout", "no sweep leg in this one"
    assert got[0].entry == 1.0930, "the return to the broken minor swing"
    assert got[0].stop == 1.0912, "the wick of the confirming candle"


def test_a_wick_through_the_minor_swing_is_not_a_break():
    """A break is a BODY close everywhere else in this course, and a
    level that has merely been tested is still the level it was."""
    level = v(1.0900)
    bars = [
        h1(0, 1.0905, 1.0910, 1.0898, 1.0902),
        h1(1, 1.0902, 1.0915, 1.0900, 1.0912),
        h1(2, 1.0912, 1.0930, 1.0910, 1.0928),
        h1(3, 1.0928, 1.0929, 1.0915, 1.0918),
        h1(4, 1.0918, 1.0920, 1.0910, 1.0914),
        h1(5, 1.0914, 1.0940, 1.0912, 1.0925),   # wicks above, closes below
    ]
    assert _run_reaction(bars, Direction.BULLISH, level) == []


def test_a_lower_low_before_the_break_makes_it_a_sweep_and_break():
    """part5 t=401-409, the one leg that differs: price "comes back down
    and makes a LOWER low, taking out the first low's liquidity", and
    then the same break follows."""
    level = v(1.0900)
    bars = [
        h1(0, 1.0905, 1.0910, 1.0898, 1.0902),   # first low 1.0898
        h1(1, 1.0902, 1.0915, 1.0900, 1.0912),
        h1(2, 1.0912, 1.0930, 1.0910, 1.0928),   # the minor swing high
        h1(3, 1.0928, 1.0929, 1.0915, 1.0918),
        h1(4, 1.0918, 1.0920, 1.0890, 1.0895),   # LOWER low: the sweep
        h1(5, 1.0895, 1.0935, 1.0893, 1.0932),   # and the break
    ]
    got = _run_reaction(bars, Direction.BULLISH, level)

    assert len(got) == 1
    assert got[0].form == "sweep_break"
    assert got[0].entry == 1.0930


def test_a_sweep_landing_before_the_swing_confirms_is_still_a_sweep():
    """The defect this was rewritten for. A swing confirms n bars after
    it forms, so the sweep leg can land in that gap. A running "lowest
    low so far" cannot tell the first low from the sweep of it, and 5.5
    silently degenerates into 5.4."""
    level = v(1.0900)
    bars = [
        h1(0, 1.0905, 1.0910, 1.0898, 1.0902),   # first low 1.0898
        h1(1, 1.0902, 1.0915, 1.0900, 1.0912),
        h1(2, 1.0912, 1.0930, 1.0910, 1.0928),   # the minor swing high
        h1(3, 1.0928, 1.0929, 1.0890, 1.0895),   # sweep, BEFORE confirmation
        h1(4, 1.0895, 1.0920, 1.0893, 1.0915),   # confirms the swing now
        h1(5, 1.0915, 1.0935, 1.0912, 1.0932),   # the break
    ]
    got = _run_reaction(bars, Direction.BULLISH, level)

    assert len(got) == 1
    assert got[0].form == "sweep_break", \
        "the sweep happened while the swing was still unconfirmed"


def test_a_new_setup_level_restarts_the_reaction():
    """The reaction being measured is the reaction at THAT level.
    Carrying swings across would break structure against the wrong
    reference."""
    w = ReactionWatch(2)
    first = v(1.0900)
    bars = [h1(0, 1.0905, 1.0910, 1.0898, 1.0902),
            h1(1, 1.0902, 1.0915, 1.0900, 1.0912),
            h1(2, 1.0912, 1.0930, 1.0910, 1.0928),
            h1(3, 1.0928, 1.0929, 1.0915, 1.0918),
            h1(4, 1.0918, 1.0920, 1.0910, 1.0914)]
    for bar in bars:
        w.push(bar, Direction.BULLISH, first)

    # the same breaking candle, but the setup has moved
    got = w.push(h1(5, 1.0914, 1.0935, 1.0912, 1.0932), Direction.BULLISH,
                 v(1.0800))
    assert got is None, "the swing belonged to the previous reaction"


def test_no_setup_means_no_confirmation():
    w = ReactionWatch(2)
    assert w.push(h1(0, 1.0905, 1.0910, 1.0898, 1.0902),
                  Direction.BULLISH, None) is None


def test_the_bearish_mirror_of_the_break():
    level = a(1.1100)
    bars = [
        h1(0, 1.1095, 1.1102, 1.1090, 1.1098),   # first high 1.1102
        h1(1, 1.1098, 1.1100, 1.1085, 1.1088),
        h1(2, 1.1088, 1.1090, 1.1070, 1.1072),   # the minor swing LOW
        h1(3, 1.1072, 1.1085, 1.1071, 1.1082),
        h1(4, 1.1082, 1.1090, 1.1080, 1.1085),   # confirms it
        h1(5, 1.1085, 1.1088, 1.1065, 1.1068),   # closes through 1.1070
    ]
    got = _run_reaction(bars, Direction.BEARISH, level)

    assert len(got) == 1
    assert got[0].form == "breakout"
    assert got[0].entry == 1.1070
    assert got[0].stop == 1.1088, "the wick of the confirming candle"
