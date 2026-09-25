"""
The sequence from 5.2, walked through candle by candle.

Written against the words rather than against the old engine, because
the old engine's `is_engulfing()` tested a two-candle price pattern for
a year while the course means a LEVEL price closed through.
"""

from __future__ import annotations

import pandas as pd

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..confirmation import (OpenCloseLevel, engulfs, open_close_level,
                            returned_to, stop_for)

T0 = pd.Timestamp("2026-01-01")


def c(i, o, h, l, cl):
    return Candle(time=T0 + pd.Timedelta(hours=i), open=o, high=h, low=l,
                  close=cl, volume=0)


def test_two_consecutive_up_candles_leave_a_level_to_be_sold_from():
    """5.2: "two consecutive up candles that is going to create for us
    an open close key level"."""
    a = c(0, 1.1000, 1.1030, 1.0995, 1.1020)
    b = c(1, 1.1020, 1.1050, 1.1015, 1.1045)
    lvl = open_close_level(a, b)

    assert lvl is not None
    assert lvl.direction == Direction.BEARISH, "up candles are broken downward"
    assert lvl.price == 1.1000, "the first candle's open is the body floor"


def test_mixed_candles_leave_no_level():
    """Consecutive and SAME DIRECTION. One of each is not a level."""
    up = c(0, 1.1000, 1.1030, 1.0995, 1.1020)
    down = c(1, 1.1020, 1.1025, 1.0990, 1.1000)
    assert open_close_level(up, down) is None
    assert open_close_level(down, up) is None


def test_a_wick_through_the_level_is_not_an_engulf():
    """The vocabulary is a CLOSE every time -- "break below the open
    close key level", "closes above this guy". A wick is a test."""
    lvl = OpenCloseLevel(T0, 1.1000, Direction.BEARISH, 1.1000, 1.1045)

    wick = c(2, 1.1020, 1.1025, 1.0980, 1.1010)   # dips under, closes above
    body = c(2, 1.1020, 1.1025, 1.0980, 1.0990)   # closes under

    assert engulfs(wick, lvl) is False
    assert engulfs(body, lvl) is True


def test_the_engulf_candle_trades_through_the_level_on_its_way_out():
    """The trap, and it is a real one -- this test was written the
    other way round first and failed.

    A candle that CLOSES through a level must TRADE through it, so
    `returned_to()` is trivially true of the engulf itself. The return
    is therefore only meaningful strictly AFTER the engulf: SLK_SPEC
    5.1, "entry is the return to it, NOT the engulfing candle"."""
    lvl = OpenCloseLevel(T0, 1.1000, Direction.BEARISH, 1.1000, 1.1045)

    engulf = c(2, 1.1020, 1.1025, 1.0960, 1.0970)
    assert engulfs(engulf, lvl) is True
    assert returned_to(engulf, lvl) is True, "it passed through on the way down"

    # Which is exactly why the search starts at engulf + 1.
    drifts = c(3, 1.0970, 1.0985, 1.0965, 1.0980)
    assert returned_to(drifts, lvl) is False

    comes_back = c(4, 1.0980, 1.1010, 1.0975, 1.1005)
    assert returned_to(comes_back, lvl) is True


def test_the_stop_is_the_far_edge_of_the_zone_being_entered():
    """Measured from Bishop's charts, 13 of 13 with zero exceptions, one
    of them a broker screenshot: entry at the zone's near edge, stop at
    its far edge (bishop_pdf_sl_measurements.md).

    This used to take the ENGULFING CANDLE's extreme, on "putting your SL
    at the low of the engulf" -- but in its own sentence, "wait for price
    to return back to the open close that the engulfing closed, putting
    your SL at the low of the engulf", "the engulf" is the open-close
    structure, not the candle that broke it."""
    bearish = OpenCloseLevel(T0, 1.1000, Direction.BEARISH, 1.1000, 1.1045)
    bullish = OpenCloseLevel(T0, 1.1000, Direction.BULLISH, 1.1000, 1.0955)
    engulf = c(2, 1.1020, 1.1035, 1.0960, 1.0970)

    assert stop_for(engulf, bearish) == 1.1045, "the zone's top, above entry"
    assert stop_for(engulf, bullish) == 1.0955, "the zone's bottom, below entry"

    # And it does NOT come from the engulfing candle any more.
    assert stop_for(engulf, bearish) != engulf.high
    assert stop_for(engulf, bullish) != engulf.low


def test_the_stop_sits_on_the_far_side_of_the_entry_in_the_normal_case():
    """The property that makes it a stop at all.

    NOT guaranteed, and the docstring here said it was until I checked: a
    second candle that gaps can close back through the first one's open,
    leaving the zone inverted. The driver refuses those orders
    (`_stop_beyond` in replay.py) rather than this function pretending
    they cannot happen."""
    bearish = OpenCloseLevel(T0, 1.1000, Direction.BEARISH, 1.1000, 1.1045)
    bullish = OpenCloseLevel(T0, 1.1000, Direction.BULLISH, 1.1000, 1.0955)
    engulf = c(2, 1.1020, 1.1035, 1.0960, 1.0970)

    assert stop_for(engulf, bearish) > bearish.price
    assert stop_for(engulf, bullish) < bullish.price


def test_the_whole_sequence_in_order():
    """Two up candles, a close through, then the return. Nothing in
    this test looks at a candle later than the one being judged."""
    bars = [
        c(0, 1.1000, 1.1030, 1.0995, 1.1020),   # up
        c(1, 1.1020, 1.1050, 1.1015, 1.1045),   # up  -> level at 1.1000
        c(2, 1.1045, 1.1048, 1.0960, 1.0970),   # closes through -> engulf
        c(3, 1.0970, 1.0990, 1.0965, 1.0985),
        c(4, 1.0985, 1.1010, 1.0980, 1.1005),   # returns -> ENTRY
    ]

    lvl = open_close_level(bars[0], bars[1])
    assert lvl is not None

    engulf_i = next(i for i in range(2, len(bars)) if engulfs(bars[i], lvl))
    assert engulf_i == 2

    entry_i = next(i for i in range(engulf_i + 1, len(bars))
                   if returned_to(bars[i], lvl))
    assert entry_i == 4

    # Entry at the zone's near edge, stop at its far edge. That is the
    # whole trade, and the risk is the distance between them -- here the
    # two up candles span 1.1000 to 1.1045, so the risk is 45 pips.
    entry = lvl.price
    stop = stop_for(bars[engulf_i], lvl)
    assert entry == 1.1000 and stop == 1.1045
    assert stop > entry, "a sell's stop sits above its entry"
