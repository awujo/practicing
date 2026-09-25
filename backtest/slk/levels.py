"""
The four key-level shapes, and what happens when price closes through one.

bias-1 t=60-180 gives the shapes:

    V-shape          buys     a swing low
    A-shape          sells    a swing high
    open-close       either   two consecutive same-direction candles
                              (built in confirmation.py, where it is used)

POLARITY FLIPS ON A CLOSE THROUGH -- bias-1 t=195-300:

    "This is what the key level should be used for UNTIL THEY GET
     DISRESPECTED. The moment [price] can close above this guy --
     remember, this was supposed to be used for sales -- that's when we
     now use it for a buy, or you can call it an engulfing."

and it applies to all four shapes, not only open-close.

Two refinements the operator gave on 2026-09-22, both of which the old
implementation had wrong:

    THE RETURN MAY OVERSHOOT.  "It can still come to the flip level too
    OR EVEN BELOW." Requiring the candle to straddle the level throws
    away every return that pokes through it, which is common and valid.

    INVALIDATION IS A BREAKOUT BACK THE OTHER WAY.  "but it must not
    create a breakout back to the opposite direction." Between the
    disrespect and the return there must be no break of structure
    against the trade -- a BODY close beyond a swing that formed AFTER
    the flip. A wick through is not enough, and a close beyond a swing
    that predates the flip is just price retracing into the level,
    which is the setup rather than its invalidation.

`n` HAS NO SOURCE AND SO HAS NO DEFAULT

Neither man ever defines a swing numerically. video-12 t=683-693 is
typical: "we have broken above this high. We have broken above all of
these structural highs" -- he is pointing at a chart. Any mechanisation
needs SOME definition, so `n` exists, but it is a number I chose and
every caller must therefore say which one it is using. A default is how
`min_stop_pips` and `min_reward_r` got in, and both had to be torn out
on the operator's instruction.

NO FUTURE

`levels_confirmed_by` is handed the candles up to now and returns only
levels whose fractal has already completed. A swing at i is not a swing
until i+n bars exist, so the last n candles can never contribute one.
That is a property of the arithmetic here, not a filter that has to
remember itself.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..engine.candles import Candle
from ..engine.structure import Direction


@dataclass(frozen=True)
class KeyLevel:
    time: object
    price: float
    shape: str                 # "V" | "A"
    bias: Direction            # the direction it is currently used for
    flipped: bool = False      # has price closed through it


def levels_confirmed_by(candles: list[Candle], n: int) -> list[KeyLevel]:
    """Every V and A shape whose fractal has completed inside `candles`.

    A swing at i needs n bars either side, so the scan stops n short of
    the end. Nothing here can see a candle that has not arrived, because
    no such candle is in the list.
    """
    out = []
    for i in range(n, len(candles) - n):
        window = candles[i - n:i + n + 1]
        here = candles[i]
        if all(here.low <= c.low for c in window) and \
                any(here.low < c.low for c in window):
            out.append(KeyLevel(here.time, here.low, "V", Direction.BULLISH))
        elif all(here.high >= c.high for c in window) and \
                any(here.high > c.high for c in window):
            out.append(KeyLevel(here.time, here.high, "A", Direction.BEARISH))
    return out


def disrespected_by(candle: Candle, level: KeyLevel) -> bool:
    """Has this candle CLOSED through the level?

    A close, every time -- "the moment [price] can CLOSE above this
    guy". A wick through is a test, and a level that has merely been
    tested is still the level it was.
    """
    if level.bias == Direction.BULLISH:
        return candle.close < level.price     # a buy level closed below
    return candle.close > level.price         # a sell level closed above


def flip(level: KeyLevel) -> KeyLevel:
    """The same price, now used the other way.

    "This was supposed to be used for sales -- that's when we now use
    it for a buy." The price does not move; what changes is which side
    of it you are looking to trade from.
    """
    other = (Direction.BEARISH if level.bias == Direction.BULLISH
             else Direction.BULLISH)
    return replace(level, bias=other, flipped=True)


def returned_to(candle: Candle, level: KeyLevel) -> bool:
    """Has price come back to the level, including through it?

    Operator, 2026-09-22: "It can still come to the flip level too OR
    EVEN BELOW." So a bullish level is reached the moment the candle's
    low gets to it -- whether it stops there, or overshoots.
    """
    if level.bias == Direction.BULLISH:
        return candle.low <= level.price
    return candle.high >= level.price


def broke_back(candles: list[Candle], flip_idx: int, now_idx: int,
               direction: Direction, n: int) -> bool:
    """Did price break structure AGAINST `direction` since the flip?

    "It must not create a breakout back to the opposite direction."

    A breakout is read the same way it is read everywhere else: a BODY
    close beyond a confirmed swing. And only swings formed AFTER the
    flip count -- a close beyond one that predates it is price
    retracing into the level, which is the setup, not its end.
    """
    if now_idx <= flip_idx:
        return False
    window = candles[:now_idx + 1]
    against = (Direction.BEARISH if direction == Direction.BULLISH
               else Direction.BULLISH)

    for lvl in levels_confirmed_by(window, n):
        # Formed after the flip, and pointing against the trade.
        if lvl.time <= candles[flip_idx].time:
            continue
        if against == Direction.BEARISH and lvl.shape == "V":
            if any(c.close < lvl.price for c in window if c.time > lvl.time):
                return True
        elif against == Direction.BULLISH and lvl.shape == "A":
            if any(c.close > lvl.price for c in window if c.time > lvl.time):
                return True
    return False
