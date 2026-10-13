"""Entry model tests on hand-built and random-walk prices (no network)."""
import numpy as np
import pandas as pd

from slk.candles import resample
from slk.entry import find_entries, patterns, _arrays
from slk.story import find_stories

from test_engine import walk

P = 0.0001
T0 = pd.Timestamp("2020-01-06 00:00", tz="UTC")  # Monday


def mk(rows):
    """rows of (open, high, low, close) in pips above 1.1000 -> H1 frame."""
    idx = pd.date_range(T0, periods=len(rows), freq="h")
    a = 1.1 + np.array(rows, dtype=float) * P
    return pd.DataFrame(a, index=idx, columns=["open", "high", "low", "close"])


def leg(frm, to, n):
    """n bars moving from frm to to (pips), 1-pip wicks."""
    out, c = [], frm
    for k in range(1, n + 1):
        o, c = c, frm + (to - frm) * k / n
        out.append((o, max(o, c) + 1, min(o, c) - 1, c))
    return out


def pattern_sell(at):
    """c1 bull to `at`, c2 bear, c3 wick 3 pips above the line then closes below, c4 impulsive bear."""
    return [(at - 5, at + 0.5, at - 6, at),            # c1 bull, close = line
            (at, at + 0.5, at - 6, at - 5),            # c2 bear
            (at - 5, at + 3, at - 7, at - 7),          # c3 rejects: high above line, close below
            (at - 7, at - 7, at - 30, at - 29)]        # c4 impulsive close below c1..c3 lows


def story_row(h1, **kw):
    r = {"pair": "EURUSD", "story": "D", "side": "SELL", "level": 1.2, "target": 1.1 - 120 * P,
         "tap_time": str(h1.index[0])[:16], "breakout_time": str(h1.index[2])[:16],
         "confirm_time": str(h1.index[3])[:16]}
    r.update(kw)
    return r


H1ONLY = {"entry_tfs": {"D": ["H1"], "W": ["H1"], "M": ["H1"]}}


def scenario(retest=True, second=False):
    rows = leg(40, 20, 4)                     # 0-3: breakout leg (bar 2 = external break)
    rows += leg(20, 30, 3)                    # 4-6: first retracement up (top at bar 6)
    rows += leg(30, 10, 4)                    # 7-10
    rows += pattern_sell(15)                  # 11-14: pattern, line at +15
    rows += leg(-14, -10, 2)                  # 15-16 small bounce, no retest yet
    if second:
        rows += leg(-10, 0, 2)                # 17-18 up into a second A-shape
        rows += pattern_sell(2)               # 19-22: newer pattern, line at +2
        rows += leg(-27, -20, 2)
    if retest:
        top = 2 if second else 15
        rows += leg(rows[-1][3], top - 1, 3)  # rally that ends 1 pip under the line
        rows.append((top - 1, top + 0.5, top - 2, top - 1))  # touches the line (fill), no stop
    rows += leg(rows[-1][3], -130, 12)        # sell-off to the target
    rows += leg(-130, -130, 30)
    return mk(rows)


def test_h2_bins_on_17ny_grid():
    d = resample(walk(24 * 10), "H2")
    st = pd.to_datetime(d["start"])
    ny = st.dt.tz_convert("America/New_York")
    assert set(ny.dt.hour % 2) == {1}          # 17:00, 19:00, ... New York
    assert (pd.to_datetime(d["end"]) - st).max() == pd.Timedelta(hours=2)


def test_pattern_detection():
    h1 = mk(leg(0, 10, 10) + pattern_sell(15))
    B = _arrays(resample(h1, "H1"))
    cfg = {"tap_tol_pips": 1.0, "impulse_mult": 1.0, "impulse_lookback": 10}
    pats = patterns(B, True, cfg, P)
    assert [p["c1"] for p in pats] == [10]
    assert abs(pats[0]["line"] - (1.1 + 15 * P)) < 1e-9 and abs(pats[0]["c3x"] - (1.1 + 18 * P)) < 1e-9
    # c3 closing above the line is not a rejection
    rows = leg(0, 10, 10) + pattern_sell(15)
    rows[12] = (10, 18, 8, 16)
    assert patterns(_arrays(resample(mk(rows), "H1")), True, cfg, P) == []
    # c4 that does not close beyond c1..c3 lows is not a breakout
    rows = leg(0, 10, 10) + pattern_sell(15)
    rows[13] = (8, 8, 7, 7.5)
    assert patterns(_arrays(resample(mk(rows), "H1")), True, cfg, P) == []
    assert patterns(B, False, cfg, P) == []    # no V-shape buy pattern here


def test_triggered_entry_stop_tp():
    h1 = scenario()
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    assert e["status"] == "TRIGGERED" and e["tf"] == "H1"
    assert abs(e["entry"] - (1.1 + 15 * P)) < 1e-9
    assert abs(e["stop"] - (1.1 + 19 * P)) < 1e-9 and e["stop_pips"] == 4.0
    assert e["tp1"] <= e["entry"] - 1.5 * 4 * P + 1e-9 and e["tp2"] == 1.1 - 120 * P
    assert e["tp1_outcome"] == "win" and e["tp2_outcome"] == "win"
    assert e["tp2_R"] == e["R_tp2"] == round(135 / 4, 2)


def test_skip_first_retracement():
    h1 = scenario()
    # a breakout so late that the pattern sits before the first retracement top -> no setup on H1
    late = story_row(h1, breakout_time=str(h1.index[10])[:16], confirm_time=str(h1.index[11])[:16])
    e = find_entries("EURUSD", h1, [late], H1ONLY)[0]
    assert e["status"] == "NO_SETUP"
    e = find_entries("EURUSD", h1, [late], {**H1ONLY, "skip_first": False})[0]
    assert e["status"] == "TRIGGERED"


def test_missed_when_no_retest():
    h1 = scenario(retest=False)
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    assert e["status"] == "MISSED" and "tp1_R" not in e


def test_newer_level_replaces_older():
    h1 = scenario(second=True)
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    assert e["status"] == "TRIGGERED" and e["candidates"] == 2
    assert abs(e["entry"] - (1.1 + 2 * P)) < 1e-9


def test_filters_wide_stop_and_pairs():
    h1 = scenario()
    e = find_entries("EURUSD", h1, [story_row(h1)], {**H1ONLY, "max_stop_pips": 3})[0]
    assert e["status"] == "NO_SETUP" and "wide_stop 1" in e["note"]
    e = find_entries("AUDNZD", h1, [story_row(h1, pair="AUDNZD")], H1ONLY)[0]
    assert e["status"] == "SKIPPED"


def test_same_bar_stop_and_tp_is_loss():
    rows = scenario().pipe(lambda d: ((d - 1.1) / P).round(6).to_numpy().tolist())
    h1 = scenario()
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    f = list(h1.index.strftime("%Y-%m-%d %H:%M")).index(e["fill_time"])
    rows[f + 1] = [14, 25, -130, -125]        # next bar spikes through the stop and the target
    h1 = mk(rows)
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    assert e["tp1_outcome"] == "loss" and e["tp2_R"] == -1.0


def test_tf_fallback_and_random_walk():
    h1 = walk()
    for st in ("D", "W"):
        stories = find_stories("EURUSD", h1, st)
        rows = find_entries("EURUSD", h1, stories)
        assert len(rows) == len(stories)
        tfs = {"D": {"H4", "H2", "H1"}, "W": {"D", "H4"}}[st]
        for r in rows:
            assert r["status"] in ("TRIGGERED", "MISSED", "PENDING", "NO_SETUP")
            if r["status"] != "NO_SETUP":
                assert r["tf"] in tfs and 0 < r["stop_pips"] <= 20
                assert r["R_tp1"] >= 1.5 - 1e-9 or r["tp1"] == r["tp2"]
            if r["status"] == "TRIGGERED":
                assert r["tp1_R"] >= -1 and r["tp2_R"] >= -1
