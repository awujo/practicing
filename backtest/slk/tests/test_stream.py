"""
Levels confirm exactly n candles late, and never sooner.
"""

from __future__ import annotations

import random
import time

import pandas as pd

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..levels import levels_confirmed_by
from ..stream import LevelStream

T0 = pd.Timestamp("2026-01-01")


def c(i, lo, hi):
    mid = (lo + hi) / 2
    return Candle(time=T0 + pd.Timedelta(hours=i), open=mid, high=hi, low=lo,
                  close=mid, volume=0)


def test_a_level_appears_exactly_n_candles_after_the_swing_not_before():
    """The no-future guarantee, and it is structural: the later candles
    are not in the buffer yet, so there is nothing to peek at."""
    bars = [c(0, 1.10, 1.12), c(1, 1.09, 1.11),
            c(2, 1.05, 1.07),                      # the swing low
            c(3, 1.08, 1.10), c(4, 1.11, 1.13)]

    s = LevelStream(n=2)
    emitted = []
    for i, bar in enumerate(bars):
        got = s.push(bar)
        emitted.append((i, [l.price for l in got]))

    assert emitted[2] == (2, []), "the swing bar itself confirms nothing"
    assert emitted[3] == (3, []), "still one candle short"
    assert emitted[4][1] == [1.05], "confirmed when bar 4 closes -- n=2 later"


def test_the_stream_agrees_with_the_batch_detector():
    """Two implementations of one rule must not drift. If they ever
    disagree, one of them is wrong and this says so immediately."""
    random.seed(11)
    px, bars = 1.1000, []
    for i in range(400):
        px += random.gauss(0, 0.0008)
        bars.append(c(i, px - abs(random.gauss(0, .0004)),
                      px + abs(random.gauss(0, .0004))))

    s = LevelStream(n=2)
    for bar in bars:
        s.push(bar)

    batch = levels_confirmed_by(bars, n=2)
    assert [(l.time, l.price, l.shape) for l in s.standing()] == \
           [(l.time, l.price, l.shape) for l in batch]


def test_work_per_candle_does_not_grow_with_history():
    """The reason the old engine took most of an hour per instrument
    was re-scanning the whole series at every bar. Here the last candle
    of a long run must cost about what the first did."""
    random.seed(3)
    px = 1.1000
    bars = []
    for i in range(20000):
        px += random.gauss(0, 0.0008)
        bars.append(c(i, px - 0.0004, px + 0.0004))

    s = LevelStream(n=2)
    for bar in bars[:1000]:
        s.push(bar)

    t0 = time.perf_counter()
    for bar in bars[1000:2000]:
        s.push(bar)
    early = time.perf_counter() - t0

    for bar in bars[2000:19000]:
        s.push(bar)

    t0 = time.perf_counter()
    for bar in bars[19000:]:
        s.push(bar)
    late = time.perf_counter() - t0

    assert late < early * 5, f"cost grew with history: {early:.4f} -> {late:.4f}"


def test_standing_can_be_filtered_by_direction():
    bars = [c(0, 1.10, 1.12), c(1, 1.09, 1.11), c(2, 1.05, 1.07),
            c(3, 1.08, 1.10), c(4, 1.11, 1.13),
            c(5, 1.14, 1.20), c(6, 1.13, 1.16), c(7, 1.12, 1.15)]
    s = LevelStream(n=2)
    for bar in bars:
        s.push(bar)

    buys = s.standing(Direction.BULLISH)
    sells = s.standing(Direction.BEARISH)
    assert all(l.shape == "V" for l in buys)
    assert all(l.shape == "A" for l in sells)
    assert len(buys) + len(sells) == len(s.standing())
