"""Speed-ups must not change results: engine output == golden output of the engine before the speed-ups
(tests/engine_golden.py, generated at commit 49d4fb7)."""
import json

import pytest

import engine_golden as G
from slk.structure import SwingBook, pivots, swings
from test_engine import walk

GOLDEN = json.load(open(G.PATH))


@pytest.mark.parametrize("i", range(len(G.CASES)))
def test_engine_outputs_identical_to_golden(i):
    want = GOLDEN[i]
    pair, seed, hours, cfg = G.CASES[i]
    assert (want["pair"], want["seed"], want["hours"], want["cfg"]) == (pair, seed, hours, cfg)
    h1 = G.data(pair, seed, hours)
    from slk.entry import find_entries
    from slk.story import current_tap, find_stories
    for st in ("D", "W", "M"):
        s = find_stories(pair, h1, st, cfg)
        assert G._clean(s) == want["stories"][st], st
        # golden = the old engine: continuation only, breakout on c4 only; new row keys removed
        old = find_entries(pair, h1, s, {"breakout_max_bars": 1, "entry_models": ["continuation"]}, cfg, sim=True)
        old = [{k: v for k, v in r.items() if k not in ("model", "bo_candle")} for r in old]
        assert G._clean(old) == want["entries"][st], st
        find_entries(pair, h1, s, None, cfg, sim=True)  # default models run without errors
        cuts = range(len(h1) // 2, len(h1), max(1, len(h1) // 25))
        assert [G._clean(current_tap(pair, h1.iloc[:n], st, cfg)) for n in cuts] == want["taps"][st], st


def test_swingbook_equals_swings():
    c = walk(24 * 300, seed=4)["close"]
    for n in (1, 2, 3):
        piv = pivots(c, n)
        book = SwingBook(piv)
        for u in range(-2, len(c) + 3, 5):
            assert book.at(u) == swings(piv, u)


def _pivots_loop(close, n):  # the original rule, bar by bar
    import numpy as np
    c = np.asarray(close, dtype=float)
    out = []
    for i in range(n, len(c) - n):
        w = c[i - n:i + n + 1]
        if c[i] == w.max() and c[i] > c[i - 1]:
            out.append((i, "H", c[i], i + n))
        elif c[i] == w.min() and c[i] < c[i - 1]:
            out.append((i, "L", c[i], i + n))
    return out


def test_vectorised_pivots_equal_loop():
    c = walk(24 * 200, seed=6)["close"].round(3)  # rounding makes equal closes (ties) happen
    for n in (1, 2, 3, 5):
        assert pivots(c, n) == _pivots_loop(c, n)
    assert pivots([1.0, 2.0], 2) == [] and pivots([1, 3, 2], 1) == _pivots_loop([1, 3, 2], 1)
