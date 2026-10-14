"""Examples diagnosis (2026-10-14, REVIEW.md "Examples diagnosis (cTrader data)"): Kevin's worked examples on the
offline IC Markets cTrader H1 candles in data/examples, and the four rule changes it made (each one switched back
reproduces the engine before it: tests/golden/engine_golden_v07.json)."""
import json
import os

import numpy as np
import pandas as pd

import engine_golden as G
from slk import story as S
from slk import verify_examples as V
from slk.live import build_cfg

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "examples")


def _ctx(pair, now, **over):
    h1 = V.load_csv(pair, DATA)
    return S._Ctx(pair, h1[h1.index < pd.Timestamp(now, tz="UTC")], "D", {**S.DEFAULT, **over})


def _bar(X, start):
    return int(np.flatnonzero(pd.to_datetime(X.o_start) == pd.Timestamp(start, tz="UTC"))[0])


def test_offline_csv_loads():
    h1 = V.load_csv("CADJPY", DATA)
    assert list(h1.columns) == ["open", "high", "low", "close"] and str(h1.index.tz) == "UTC"
    assert h1.index.is_monotonic_increasing and len(h1) > 20000


def test_switches_back_reproduce_v07_golden():
    """Every change in engine_golden.json comes from the four examples-diagnosis rules."""
    gold = json.load(open(G.PATH_V07))
    for i in (0, 2, 5):
        pair, seed, hours, cfg = G.CASES[i]
        h1 = G.data(pair, seed, hours)
        c = {**G.PRE_EXAMPLES, **cfg}
        for st in ("D", "W"):
            assert G._clean(G.strip_labels(S.find_stories(pair, h1, st, c))) == gold[i]["stories"][st], (i, st)


def test_pullback_level_cadjpy_jan_8():
    """story-line-pt2@1420-1580: CADJPY D is retracing in a weekly uptrend ("these are just retracement"); the buy
    level tapped Thu Jan 8 2026 starts the story. Without pullback_levels the D trend (down) blocks it."""
    X = _ctx("CADJPY", "2026-02-07")
    b = _bar(X, "2026-01-07 22:00")
    tr = S.trend(X.osw.at(b - 1), X.O["close"][b - 1])
    assert tr == "down" and X.htf_trend(X.o_start[b]) == "up"
    lv = X.choose(b, tr)
    assert lv is not None and lv.side == "buy" and abs(lv.price - 112.903) <= 0.15
    X.cfg = {**X.cfg, "pullback_levels": False}
    assert X.choose(b, tr) is None or X.choose(b, tr).side == "sell"


def test_cadjpy_rule_on_feb_2():
    """cadjpy-bd@599-739, F cadjpy-bd/sheet_008-009: Mon Feb 2 2026 sweeps the Jan 30 low into the daily open-close
    level ~113.2 of the zone the daily flipped (A sell 113.148 closed through on Jan 29): the exception fires on that
    OC level (not on the newer flip levels the wick also hit)."""
    X = _ctx("CADJPY", "2026-02-04")
    b = _bar(X, "2026-02-01 22:00")
    lv = X.choose(b, "up")
    assert lv.kind == "OC" and abs(lv.price - 113.2) <= 0.1 and X.cadjpy(lv, b, X.htf_trend(X.o_start[b]))
    old = _ctx("CADJPY", "2026-02-04", cadjpy_zone=False)
    assert old.choose(b, "up").kind == "flip"  # v0.6 picked the newest level (113.597), not his OC


def test_tap_must_reach_the_line_gbpjpy_jan_16():
    """story-line-pt4@1315-1335 ('traded close to the open close key level but did not enter it'): a wick 0.2 pip
    short is no tap. GBPJPY Fri Jan 16 2026: low 211.388 vs the flip level 211.386."""
    X = _ctx("GBPJPY", "2026-01-20 04:00")
    b = _bar(X, "2026-01-15 22:00")
    assert not any(abs(l.price - 211.386) < 0.001 for l in X.taps.get(b, ()))
    Y = _ctx("GBPJPY", "2026-01-20 04:00", tap_tol_pips=1.0)
    assert any(abs(l.price - 211.386) < 0.001 for l in Y.taps.get(b, ()))


def test_alignment_ends_at_retap_gbpjpy():
    """story-line-pt4@622-765: the Jan 19 tap of the V 210.809 is a new daily story (B = the last A before it), not
    the alignment chain from Jan 12."""
    h1 = V.load_csv("GBPJPY", DATA)
    h1 = h1[h1.index < pd.Timestamp("2026-01-20 04:00", tz="UTC")]
    last = S.find_stories("GBPJPY", h1, "D")[-1]
    assert last["rule"] == "standard" and abs(last["level"] - 210.809) < 0.02 and last["tap_time"] == "2026-01-18 22:00"
    old = S.find_stories("GBPJPY", h1, "D", {"align_retap_ends": False})[-1]
    assert old["rule"] == "alignment"


def test_examples_on_offline_data():
    cfg = build_cfg()[0]
    res = {ex["id"]: V.check(ex, V.load_csv(ex["pair"], DATA), cfg)[0] for ex in V.EXAMPLES}
    for i in ("cadjpy-d-buy", "cadjpy-d-buy-no-h4-exception", "eurgbp-d-buy-overlap", "usdcad-d-sell-friday-sweep",
              "usdjpy-d-no-h4-breakout", "usdchf-d-reject-no-h4"):
        assert res[i] == "PASS", i
