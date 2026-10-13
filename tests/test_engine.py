"""Smoke and rule tests on synthetic prices (no network)."""
import numpy as np
import pandas as pd

from slk.candles import resample
from slk.levels import Level, run_levels
from slk.story import find_stories
from slk.structure import pivots, swings, trend


def walk(n=24 * 900, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    c = 1.1 + np.cumsum(rng.normal(0, 0.0012, len(idx)))
    o = np.r_[c[0], c[:-1]]
    w = np.abs(rng.normal(0, 0.0006, len(idx)))
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + w, "low": np.minimum(o, c) - w, "close": c}, index=idx)


def test_daily_close_is_17_ny():
    d = resample(walk(24 * 20), "D")
    # bars start at 17:00 New York = 21:00 or 22:00 UTC
    st = pd.to_datetime(d["start"]).iloc[1:]
    st = st[st.dt.dayofweek != 0]  # synthetic data has no Sunday-evening hours
    assert set(st.dt.hour) <= {21, 22}


def test_trend_and_pivots():
    c = [1, 2, 3, 2, 1.5, 2.5, 3.5, 2.8, 2.2, 3, 4, 3.5]
    sw = swings(pivots(c, 1), 99)
    assert trend(sw, 3.5) == "up"


def test_wick_tap_vs_body_break():
    bars = pd.DataFrame({"open": [1.0, 1.0, 1.0], "high": [1.0, 1.3, 1.0], "low": [0.9, 0.9, 0.9], "close": [1.0, 1.0, 1.25]})
    lv = run_levels(bars, [Level(1.2, "sell", "A", 1)], 0.0)
    assert lv[0].events[0][1] == "tap"            # wick through, close back = tap (used)
    assert lv[0].events[1][1] == "break"          # later body close through = break
    assert lv[1].side == "buy" and lv[1].kind == "flip"


def test_stories_run():
    h1 = walk()
    for st in ("D", "W"):
        rows = find_stories("EURUSD", h1, st)
        for r in rows:
            assert r["stop_pips"] > 0 and r["outcome"] in ("win", "loss", "timeout", "flip")
    assert len(find_stories("EURUSD", h1, "D")) > 0
