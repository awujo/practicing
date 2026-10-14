"""level_tol_pips (broker tolerance for wick touches): 0 = the golden engine output exactly; N widens only wick
tests (tap / fresh / first touch / re-taps), never closes (a break of a level or of point B is a real close)."""
import json

import numpy as np
import pandas as pd
import pytest

import engine_golden as G
from slk import settings as S
from slk.candles import resample
from slk.levels import Level, run_levels, touch_tol
from slk.story import DEFAULT, STORIES, current_tap, find_stories

GOLDEN = json.load(open(G.PATH))


@pytest.mark.parametrize("i", [0, 2, 4])
def test_zero_tolerance_equals_golden(i):
    pair, seed, hours, cfg = G.CASES[i]
    want = GOLDEN[i]
    h1 = G.data(pair, seed, hours)
    cfg0 = {**G.pinned(cfg), "level_tol_pips": 0.0}
    for st in ("D", "W", "M"):
        assert G._clean(G.strip_labels(find_stories(pair, h1, st, cfg0))) == want["stories"][st], st
        cuts = range(len(h1) // 2, len(h1), max(1, len(h1) // 25))
        assert [G._clean(G.strip_labels(current_tap(pair, h1.iloc[:n], st, cfg0))) for n in cuts] == want["taps"][st]


def test_level_tol_adds_to_tap_tolerance():
    # golden case 5 was made with tap_tol_pips=3: tap_tol 1 + level_tol 2 must give the same stories
    pair, seed, hours, cfg = G.CASES[5]
    assert cfg["tap_tol_pips"] == 3.0
    h1 = G.data(pair, seed, hours)
    cfg2 = {**G.pinned(cfg), "tap_tol_pips": 1.0, "level_tol_pips": 2.0}
    for st in ("D", "W"):
        assert G._clean(G.strip_labels(find_stories(pair, h1, st, cfg2))) == GOLDEN[5]["stories"][st], st


def _bars(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_wick_short_of_line_taps_only_with_tolerance():
    P = 0.0001
    # sell level 1.1000: bar 1 wick reaches 1.09985 (1.5 pips short); bar 2 closes 0.5 pip ABOVE (= break)
    b = _bars([(1.0950, 1.0960, 1.0940, 1.0955), (1.0960, 1.09985, 1.0955, 1.0970), (1.0970, 1.1010, 1.0965, 1.10005)])
    for tol_pips, want in ((0.0, [(2, "break", False)]), (2.0, [(1, "tap", True), (2, "break", False)])):
        lv = Level(1.1000, "sell", "A", 1)
        run_levels(b, [lv], touch_tol({"tap_tol_pips": 0.0, "level_tol_pips": tol_pips}, P))
        assert lv.events == want, tol_pips
    # a close 0.5 pip short of the line is NOT a break even with 5 pips tolerance (closes are exact)
    b2 = _bars([(1.0950, 1.0960, 1.0940, 1.0955), (1.0960, 1.1003, 1.0955, 1.09995), (1.0990, 1.0995, 1.0900, 1.0910)])
    lv = Level(1.1000, "sell", "A", 1)
    run_levels(b2, [lv], touch_tol({"tap_tol_pips": 0.0, "level_tol_pips": 5.0}, P))
    assert lv.events == [(1, "tap", True)]


def test_breakouts_are_real_closes_beyond_b_with_tolerance():
    pair, seed, hours, _ = G.CASES[1]
    h1 = G.data(pair, seed, hours)
    n = 0
    for st in ("D", "W"):
        cb = resample(h1, STORIES[st][1])
        for r in find_stories(pair, h1, st, {"level_tol_pips": 5.0}):
            if r["rule"].startswith(("cadjpy", "alignment")):
                continue
            k = cb.index[cb["start"].astype(str).str[:16] == r["breakout_time"]][0]
            c = cb["close"].iat[k]
            assert (c < r["B"]) if r["side"] == "SELL" else (c > r["B"]), r  # strictly beyond B, no tolerance
            n += 1
    assert n > 0


def test_level_tol_changes_something_but_defaults_unchanged():
    pair, seed, hours, _ = G.CASES[0]
    h1 = G.data(pair, seed, hours)
    base = find_stories(pair, h1, "D", {})
    wide = find_stories(pair, h1, "D", {"level_tol_pips": 5.0})
    assert base != wide  # the setting is wired in
    assert DEFAULT["level_tol_pips"] == 0.0


def test_setting_schema():
    spec = next(s for s in S.SCHEMA if s["name"] == "level_tol_pips")
    assert spec["default"] == "0" and spec["min"] == 0 and spec["max"] == 5 and spec["group"] == "Bias rules"
    assert S.story_cfg(S.load({}))["level_tol_pips"] == 0.0
    assert S.story_cfg(S.load({"level_tol_pips": "2"}))["level_tol_pips"] == 2.0
    with pytest.raises(ValueError):
        S.clean("level_tol_pips", "6")
    assert np.isclose(touch_tol({"tap_tol_pips": 1.0, "level_tol_pips": 2.0}, 0.01), 0.03)
