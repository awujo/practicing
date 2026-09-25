"""
Bias: three conditions, and there is only one rule.

bias-1 t=380-413:

    "when you're building bias with key levels, you want to see one, a
     REJECTION. Two, a CANDLE CLOSURE. And three, a BREAKOUT or break
     of structure ON THE NEXT LOWER TIMEFRAME."

video-16 t=260-340 says the same thing from the other end:

    "you want to see how price [taps] into that particular key level
     and number two, how price closes below ... So IT IS NOT ENOUGH to
     now begin to look for selling opportunities on the lower time
     frame, no. The next thing you want to do is go one time frame
     lower ... we want to see these four hours give to us a SWEEP AND
     A BREAK."

THERE IS NO SECOND MACHINE

The old engine ran two: a cascade whose flip test asked whether the
lower timeframe had STOPPED confirming the OLD direction, and a
separate alignment check asking whether it confirmed the NEW one. An
audit on 2026-09-22 justified keeping both by attributing the first to
video-16. Re-reading video-16 on 2026-09-25, it is not there. What is
there is "it is not enough", which is condition 3 being mandatory --
the positive test, again.

So condition 3 is a POSITIVE requirement and nothing else: the next
timeframe down must confirm the direction you are taking. An absence of
contrary evidence is not a confirmation, which is also why the old
cascade could flip on an empty window.

NO FUTURE

Each predicate takes candles up to now. `breakout_after` only counts
swings that have already completed, which the levels module guarantees
arithmetically rather than by filtering.
"""

from __future__ import annotations

from ..engine.candles import Candle
from ..engine.structure import Direction
from .levels import KeyLevel, levels_confirmed_by


def rejected_at(candle: Candle, level: KeyLevel) -> bool:
    """Conditions 1 AND 2 together: price reached the level, and the
    candle CLOSED back on the side the level is traded from.

    They are one observable event, not two. "How price [taps] into that
    particular key level and number two, how price closes below" -- a
    tap without the closure is a test, and a closure without the tap is
    price passing by.

    For a level used for sells (bearish), price must reach UP to it and
    close back DOWN below it. Mirrored for buys.
    """
    if level.bias == Direction.BEARISH:
        return candle.high >= level.price and candle.close < level.price
    return candle.low <= level.price and candle.close > level.price


def breakout_after(candles: list[Candle], since_idx: int,
                   direction: Direction, n: int) -> bool:
    """Condition 3: did the NEXT TIMEFRAME LOWER break structure in
    `direction` after the rejection?

    A break is a BODY close beyond a swing that completed AFTER the
    rejection -- the same reading of "breakout" used everywhere else in
    the course, and the reason a wick does not count.

    Only swings formed after `since_idx` are eligible. A close beyond
    one that predates the rejection says nothing about what the
    rejection started.
    """
    if since_idx < 0 or since_idx >= len(candles):
        return False
    after = candles[since_idx]

    for lvl in levels_confirmed_by(candles, n):
        if lvl.time <= after.time:
            continue
        later = [c for c in candles if c.time > lvl.time]
        if direction == Direction.BULLISH and lvl.shape == "A":
            if any(c.close > lvl.price for c in later):
                return True
        elif direction == Direction.BEARISH and lvl.shape == "V":
            if any(c.close < lvl.price for c in later):
                return True
    return False


def bias_established(higher: list[Candle], lower: list[Candle],
                     level: KeyLevel, n: int) -> Direction | None:
    """The direction this level has established, or None.

    `higher` is the timeframe the level lives on, `lower` the next one
    down. Both end at "now". Returns the direction only when all three
    conditions are met, in order: the rejection happened on `higher`,
    and `lower` then broke structure the same way.

    None means no bias, which is a real answer. The absence of a
    contrary signal is not a bias in this course -- condition 3 is
    something price must DO.
    """
    rejection_idx = None
    for i, candle in enumerate(higher):
        if rejected_at(candle, level):
            rejection_idx = i
            break
    if rejection_idx is None:
        return None

    # The rejection is a move AWAY from the level, so the direction it
    # establishes is the side the candle closed on.
    direction = (Direction.BEARISH if level.bias == Direction.BEARISH
                 else Direction.BULLISH)

    rejection_time = higher[rejection_idx].time
    lower_idx = next((j for j, c in enumerate(lower)
                      if c.time >= rejection_time), None)
    if lower_idx is None:
        return None

    return direction if breakout_after(lower, lower_idx, direction, n) else None
