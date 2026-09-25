"""
The confirmation entry, exactly as stated.

Operator, 2026-09-25, in one sentence that needs no interpretation:

    "once we see a confirmation -- this is an engulfing -- wait for
     price to return back to the open close that the engulfing candle
     closed [through], putting your SL at the low of the engulf."

and SLK_SPEC 5.1, from video-14:

    "Entry is the RETURN to it, not the engulfing candle."

and 5.2:

    "price is going to create for us two consecutive up candles that is
     going to create for us an open close key level ... price will not
     just engulf, price is going to break below the ... open close key
     level that was created by these two consecutive up candles ...
     Come back to this open close key level that was broken and price
     will continue to drop."

    Stop: "just going to be a little bit above this particular high."

So the sequence has four parts and they happen in this order:

    1. two consecutive same-direction candles form an OPEN-CLOSE level
    2. a later candle CLOSES THROUGH it -- that is the engulf
    3. price RETURNS to that level -- that is the entry
    4. the stop sits beyond the engulfing candle's own extreme

WHAT "ENGULF" MEANS HERE

Not the candlestick pattern. bias-1 t=271-276: "the moment [the candle]
closes above this guy ... that's when we now use it for a buy, OR YOU
CAN CALL IT AN ENGULFING." And what-next t=389-395: "an engulfing,
that's an ENGULFED OPEN CLOSE KEY LEVEL."

A level that price closed through. The old engine tested
`is_engulfing(prev, curr)` -- a two-candle price pattern -- for a year.

NO FUTURE

`find_setup` takes candles up to and including `now` and never indexes
past it. `await_return` is given one bar at a time. A setup that has
not been returned to yet simply has no entry, which is the same thing
that is true on a live chart.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..engine.candles import Candle
from ..engine.structure import Direction


@dataclass(frozen=True)
class OpenCloseLevel:
    """The level two consecutive same-direction candles leave behind.

    `price` is the boundary between their bodies -- the open of the
    first and the close of the second are the two edges, and the level
    is the one price must close through to engulf it. For two up
    candles (a level that will be SOLD from once broken downward) that
    is the lower edge: the first candle's OPEN.
    """
    time: object
    price: float
    direction: Direction      # the direction price must break it to engulf
    first_open: float
    second_close: float


def open_close_level(a: Candle, b: Candle) -> OpenCloseLevel | None:
    """The level left by two consecutive same-direction candles, or None.

    5.2: "two consecutive up candles that is going to create for us an
    open close key level". Two up candles leave a level that gets
    engulfed DOWNWARD (and is then sold from); two down candles leave
    one engulfed upward.
    """
    a_up, b_up = a.close > a.open, b.close > b.open
    a_down, b_down = a.close < a.open, b.close < b.open

    if a_up and b_up:
        # Broken downward. The body span's floor is the first open.
        return OpenCloseLevel(a.time, a.open, Direction.BEARISH, a.open, b.close)
    if a_down and b_down:
        return OpenCloseLevel(a.time, a.open, Direction.BULLISH, a.open, b.close)
    return None


def engulfs(candle: Candle, level: OpenCloseLevel) -> bool:
    """Did this candle CLOSE THROUGH the level?

    A close, not a wick -- the whole vocabulary is "closes above this
    guy" / "break below the open close key level". A wick through it is
    a test, not an engulf.
    """
    if level.direction == Direction.BEARISH:
        return candle.close < level.price
    return candle.close > level.price


def returned_to(candle: Candle, level: OpenCloseLevel) -> bool:
    """Has price come back to the engulfed level?

    "Come back to this open close key level that was broken." A touch,
    not a close: price returning INTO the level is the entry, and it
    need not close there. A bearish setup (two up candles broken
    downward) is re-entered when price trades back UP to the level.

    ONLY MEANINGFUL AFTER THE ENGULF, and the trap is worth stating
    because the first test of it was written the wrong way round: a
    candle that CLOSES through a level must TRADE through it, so this
    is trivially true of the engulfing candle itself. Callers begin the
    search at engulf + 1 -- "entry is the return to it, NOT the
    engulfing candle" (5.1).
    """
    return candle.low <= level.price <= candle.high


def stop_for(engulf: Candle, level: OpenCloseLevel) -> float:
    """The stop: the FAR EDGE of the open-close zone being entered.

    Measured from Bishop's own charts rather than inferred from words,
    because inferring it from words is how it was got wrong. The
    chart-examples PDF was read page by page (knowledge-base/
    supplementary/bishop_pdf_sl_measurements.md) and the rule holds on
    13 of 13 measured trades with zero exceptions:

        ENTRY = NEAR edge of the risk-side zone
        STOP  = FAR edge of that same zone
        (and it is trigger-INDEPENDENT: engulfing, 4th-man, breakout and
         breakout-with-idm all show it)

    One of them is a broker screenshot, which is as hard as evidence
    gets -- p5-6 EURCHF: BUY LIMIT 0.93193, SL 0.93147, TP 0.93704. The
    zone is 0.93147-0.93193; the entry is its top and the stop its
    bottom. Risk 4.6 pips, R:R 11.1.

    The zone IS this open-close key level. For a buy the two candles are
    bearish, so `first_open` is its top (the entry, reached first coming
    down) and `second_close` its bottom (the stop). For a sell the two
    candles are bullish and it mirrors exactly. So both edges were
    already here; the stop was simply being taken from the wrong object.

    WHAT THIS REPLACES, AND WHY THAT WAS A MISREADING

    This used to return the ENGULFING CANDLE's far side, on the
    operator's "putting your SL at the low of the engulf" (2026-09-25).
    Read again in its own sentence -- "wait for price to return back to
    the open close that the engulfing closed, putting your SL at the low
    of the engulf" -- "the engulf" is the open-close structure under
    discussion, not the candle that broke it. The measured evidence and
    the operator's instruction were never in conflict; the
    implementation just took the wrong low.

    Still no padding, and still no pip figure. The far edge is a price
    the market drew.
    """
    return level.second_close
