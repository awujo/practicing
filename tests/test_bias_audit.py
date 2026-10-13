"""Bias audit (REVIEW.md "Bias audit"): structural swings, point B, the sweep-of-previous-candle start."""
import numpy as np
import pandas as pd

from slk.candles import resample
from slk.levels import sweep_taps
from slk.story import _point_b, find_stories
from slk.structure import pivots, structural_swings, swings, trend
from tests.test_engine import walk

# idx:  0  1  2    3    4    5    6    7    8    9   10   11   12   13   14   15   16   17
C = [1, 2, 3, 2.5, 2.7, 2.4, 3.5, 3.2, 3.4, 3.0, 4.0, 3.6, 3.8, 3.1, 2.9, 3.3, 2.0, 2.5]


def test_structural_swings_follow_kevin():
    sw = [(i, k, float(p), at) for i, k, p, at in structural_swings(C, pivots(C, 1))]
    # (the first swings are the start-up of the walk); 10 breaks 3.5 -> HL 3.0 at 10, and the
    # lower high 3.4 inside that pullback (idx 8) is NOT a swing; 14 closes below the HL 3.0 -> BMS fixes the
    # high 4.0; 16 breaks the pending low 2.9 -> lower high 3.3 fixed.
    assert sw[-5:] == [(6, "H", 3.5, 10), (9, "L", 3.0, 10), (10, "H", 4.0, 14), (14, "L", 2.9, 16),
                       (15, "H", 3.3, 16)]
    assert all(a[1] != b[1] for a, b in zip(sw, sw[1:]))      # strictly alternating
    assert 8 not in [s[0] for s in sw] and 12 not in [s[0] for s in sw]  # pullback wiggles ignored
    assert trend(swings(structural_swings(C, pivots(C, 1)), 16), C[16]) == "down"


def test_structural_swings_no_look_ahead():
    c = walk(24 * 200, seed=8)["close"].to_numpy()
    full = structural_swings(c, pivots(c, 2))
    for n in range(50, len(c), 97):
        part = structural_swings(c[:n], pivots(c[:n], 2))
        assert part == [s for s in full if s[3] <= n - 1]
    assert [s[3] for s in full] == sorted(s[3] for s in full)


def test_point_b_is_before_first_touch():
    sw = [(3, "L", 1.0, 4), (5, "H", 1.2, 6), (7, "L", 1.1, 8), (9, "L", 1.05, 10)]
    assert _point_b(sw, 9, True) == 1.1          # the low made at/after the touch bar (idx 9) is the rejection's own
    assert _point_b(sw, 10, True) == 1.05
    assert _point_b(sw, 3, True) is None
    assert _point_b(sw, 9, False) == 1.2


def test_sweep_taps():
    bars = pd.DataFrame({"open": [1.0, 1.05, 1.08, 1.0], "high": [1.1, 1.12, 1.09, 1.02],
                         "low": [0.95, 1.0, 0.99, 0.97], "close": [1.05, 1.08, 1.0, 1.01]})
    got = [(lv.side, lv.price, lv.born, lv.kind) for lv in sweep_taps(bars)]
    # bar 1: wick above 1.10, close 1.08 back below -> sell; bar 3: wick below 0.99, close 1.01 above -> buy
    assert got == [("sell", 1.1, 1, "sweep"), ("buy", 0.99, 3, "sweep")]


def test_sweep_start_stories():
    h1 = walk(24 * 900, seed=1)
    ob = resample(h1, "D")
    on = find_stories("EURUSD", h1, "D")
    off = find_stories("EURUSD", h1, "D", {"sweep_start": False})
    assert all(r["level_kind"] != "sweep" for r in off)
    sw = [r for r in on if r["level_kind"] == "sweep"]
    assert sw, "the alternative start must produce stories on 900 days of random walk"
    st = pd.to_datetime(ob["start"]).dt.strftime("%Y-%m-%d %H:%M").tolist()
    for r in sw:
        j = st.index(r["tap_time"])
        if r["side"] == "SELL":   # tap bar wicked above the previous day's high and closed back below it
            assert np.isclose(r["level"], ob["high"].iat[j - 1]) and ob["high"].iat[j] > r["level"] > ob["close"].iat[j]
            assert r["B"] < r["level"]
        else:
            assert np.isclose(r["level"], ob["low"].iat[j - 1]) and ob["low"].iat[j] < r["level"] < ob["close"].iat[j]
            assert r["B"] > r["level"]


def test_verify_examples_offline(tmp_path, monkeypatch):
    """The replay checker runs end to end on synthetic candles (real candles only on Actions)."""
    from slk import verify_examples as V
    h1 = walk(24 * 1200, seed=2)
    h1.index = h1.index + (pd.Timestamp("2026-02-10", tz="UTC") - h1.index[-1])  # end inside the examples' dates
    monkeypatch.setattr(V, "load", lambda pair, now: h1 * (100 if pair.endswith("JPY") else 1))
    assert V.main(["--out", str(tmp_path)]) == 0
    text = (tmp_path / "EXAMPLES.md").read_text()
    assert text.count("| **") == len(V.EXAMPLES) and "ERROR" not in text
    assert "cadjpy-d-buy" in text and "story-line-pt2@686-1980" in text
