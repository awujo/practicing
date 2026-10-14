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
    # next_day_rule flag (the default when this was written): the Jan 19 story breaks out inside the tap day, so
    # "require" (default since 2026-10-14) drops it, which is checked below
    flag = {"next_day_rule": "flag"}
    last = S.find_stories("GBPJPY", h1, "D", flag)[-1]
    assert last["rule"] == "standard" and abs(last["level"] - 210.809) < 0.02 and last["tap_time"] == "2026-01-18 22:00"
    assert last["next_day"] is False
    old = S.find_stories("GBPJPY", h1, "D", {**flag, "align_retap_ends": False})[-1]
    assert old["rule"] == "alignment"
    # require: no D story at all from Jan 12 on (Kevin at the Jan 20 class: "breakout has not been confirmed")
    assert all(r["tap_time"] < "2026-01-12" for r in S.find_stories("GBPJPY", h1, "D"))


PASS_BEFORE = ("cadjpy-d-buy", "cadjpy-d-buy-no-h4-exception", "eurgbp-d-buy-overlap", "usdcad-d-sell-friday-sweep",
               "usdjpy-d-no-h4-breakout", "usdchf-d-reject-no-h4")


def test_examples_on_offline_data():
    """Defaults (2026-10-14: next_day_rule require, trend_mode leg): 8/9. The examples-diagnosis passes still pass
    with the old trend definition; with `leg` USDCAD is the one known difference (REVIEW "Weekly trend definition":
    on IC the weekly closed above its last A-shape 1.3798 on Jan 9 2026, so W is up and the D SELL is against it)."""
    cfg = build_cfg()[0]
    assert cfg["trend_mode"] == "leg" and cfg["next_day_rule"] == "require"
    res = {ex["id"]: V.check(ex, V.load_csv(ex["pair"], DATA), cfg)[0] for ex in V.EXAMPLES}
    for i in PASS_BEFORE + ("euraud-sells", "gbpaud-sells", "gbpjpy-d-no-h4-breakout"):
        if i != "usdcad-d-sell-friday-sweep":
            assert res[i] == "PASS", i
    assert res["usdcad-d-sell-friday-sweep"] == "FAIL"
    old = {**cfg, "trend_mode": "protected"}
    for i in PASS_BEFORE + ("gbpjpy-d-no-h4-breakout",):
        ex = next(e for e in V.EXAMPLES if e["id"] == i)
        assert V.check(ex, V.load_csv(ex["pair"], DATA), old)[0] == "PASS", i


def test_weekly_leg_trend_euraud_gbpaud():
    """weekly-recap@343-376 + F sheet_005/008: the weekly BOS is a W close below the LAST V-shape of the leg.
    EURAUD: V 1.72229 (IC; Kevin 1.71717, base of the Mar 2025 rally), first W close below = week of Jan 19 2026
    (1.7144). GBPAUD: last V 2.03864 (Sep 2025; Kevin 2.0362), close below in the week of Oct 27 2025. The old
    `protected` reading kept both W trends up (EURAUD protected low 1.6026 from Nov 2024)."""
    from slk.candles import resample
    from slk.structure import swings, trend
    for pair, after, prot in (("EURAUD", "2026-01-18", 1.72229), ("GBPAUD", "2025-10-26", 2.03864)):
        w = resample(V.load_csv(pair, DATA), "W")
        st = pd.to_datetime(w["start"]).astype(str).str[:10].tolist()  # week start (Sunday UTC)
        i1, end = st.index(after), st.index("2026-02-15")
        c = w["close"].to_numpy()
        leg = S._structure(w, {**S.DEFAULT, "trend_mode": "leg"}, "W")
        # the V is a leg swing, broken by a close at that week (= the swing after it is fixed there)
        assert any(s[1] == "L" and abs(s[2] - prot) < 1e-5 for s in leg), pair
        assert c[i1] < prot and min(c[:i1][-20:]) >= prot, pair
        assert all(trend(swings(leg, i), c[i]) == "down" for i in range(i1, end + 1)), pair
        old = S._structure(w, {**S.DEFAULT, "trend_mode": "protected"}, "W")
        assert trend(swings(old, i1), c[i1]) == "up", pair
    w = resample(V.load_csv("EURAUD", DATA), "W")  # EURAUD: up the week before (no whipsaw in the 2025 range)
    i0 = pd.to_datetime(w["start"]).astype(str).str[:10].tolist().index("2026-01-11")
    leg = S._structure(w, {**S.DEFAULT, "trend_mode": "leg"}, "W")
    assert all(trend(swings(leg, i), w["close"].iat[i]) == "up" for i in range(i0 - 35, i0 + 1))
