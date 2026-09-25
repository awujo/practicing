"""
Levels as they confirm, one candle at a time.

This is the piece that makes the replay both honest and fast, and the
two come from the same property.

HONEST: a swing at index i is not a swing until n bars sit either side
of it. Fed one candle at a time, the detector can only ever emit a
level whose right-hand side has already arrived -- so a level cannot
exist before the market made it. Not a filter that has to remember to
bound itself; there is simply nothing later in the buffer to look at.

FAST: the alternative is re-scanning the series at every bar, which is
O(n^2) and is why a full-history run took most of an hour per
instrument. Here each new candle does a fixed amount of work regardless
of how much history precedes it, which is also how a live bot has to
work -- it gets one candle and must answer before the next.

The operator on 2026-09-25: "I don't like ... the time this backtesting
is using to run. How in real work use it will not be causing lateness."
Those are the same complaint, and this answers both.
"""

from __future__ import annotations

from collections import deque

from ..engine.candles import Candle
from ..engine.structure import Direction
from .levels import KeyLevel


class LevelStream:
    """Feed it closed candles; it yields key levels as they confirm.

    `n` is the fractal width. A candle is a swing when it is the
    extreme of the 2n+1 window centred on it, so the answer is known
    exactly n candles after that one closes -- never sooner, and this
    class cannot be made to answer sooner because the later candles do
    not exist in it yet.
    """

    def __init__(self, n: int = 2):
        self.n = n
        self._buf: deque[Candle] = deque(maxlen=2 * n + 1)
        self.levels: list[KeyLevel] = []

    def push(self, candle: Candle) -> list[KeyLevel]:
        """Add one closed candle. Returns any level it just confirmed.

        Returns a list rather than an Optional because a single candle
        can complete both a high and a low in degenerate data, and
        silently dropping one would be a bug nobody would see.
        """
        self._buf.append(candle)
        if len(self._buf) < self._buf.maxlen:
            return []

        window = list(self._buf)
        mid = window[self.n]
        found = []

        if all(mid.low <= c.low for c in window) and \
                any(mid.low < c.low for c in window):
            found.append(KeyLevel(mid.time, mid.low, "V", Direction.BULLISH))
        if all(mid.high >= c.high for c in window) and \
                any(mid.high > c.high for c in window):
            found.append(KeyLevel(mid.time, mid.high, "A", Direction.BEARISH))

        self.levels.extend(found)
        return found

    def standing(self, direction: Direction | None = None) -> list[KeyLevel]:
        """Levels confirmed so far, newest last.

        No recency window and no cap. The course does not give one --
        a level stands until it is disrespected, and inventing a
        lookback here would be the same species of made-up number as
        the ones already removed from the system.
        """
        if direction is None:
            return list(self.levels)
        return [l for l in self.levels if l.bias == direction]
