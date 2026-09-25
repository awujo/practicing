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

import bisect
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

    NO DEFAULT, deliberately. The course never defines a swing
    numerically -- video-12 t=683-693 points at a chart, "we have
    broken above all of these structural highs" -- so `n` is a number I
    chose, and a caller that has not thought about which one it wants
    should not compile. How much the system depends on it is a
    question to MEASURE once the replay runs, not to settle by picking
    a value that looks reasonable.
    """

    def __init__(self, n: int):
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


class BreakTracker:
    """Which swings have been closed through, and when they formed.

    Keeps only what the question needs: for each direction, the FORMATION
    time of the newest swing that a later close has gone beyond. That one
    number answers "was structure broken after T" for every T at once.

    Swings are held sorted by price and consumed by bisect, so each candle
    costs the levels it actually broke and nothing else.
    """

    def __init__(self, n: int):
        self._levels = LevelStream(n)
        self._highs: list[tuple[float, object]] = []   # A-shapes, broken by a close ABOVE
        self._lows: list[tuple[float, object]] = []    # V-shapes, broken by a close BELOW
        self.newest_break: dict[Direction, object] = {}

    def push(self, candle: Candle):
        """One closed candle of the lower timeframe."""
        for lvl in self._levels.push(candle):
            target = self._highs if lvl.shape == "A" else self._lows
            bisect.insort(target, (lvl.price, lvl.time), key=lambda p: p[0])

        # A close above an A-shape is a bullish break of structure.
        cut = bisect.bisect_left(self._highs, candle.close, key=lambda p: p[0])
        for _, when in self._highs[:cut]:
            self._bump(Direction.BULLISH, when)
        del self._highs[:cut]

        cut = bisect.bisect_right(self._lows, candle.close, key=lambda p: p[0])
        for _, when in self._lows[cut:]:
            self._bump(Direction.BEARISH, when)
        del self._lows[cut:]

    def _bump(self, direction: Direction, when):
        current = self.newest_break.get(direction)
        if current is None or when > current:
            self.newest_break[direction] = when

    def broke_after(self, when, direction: Direction) -> bool:
        """Has a swing that FORMED after `when` since been closed through?"""
        newest = self.newest_break.get(direction)
        return newest is not None and newest > when
