import os

import numpy as np
import pandas as pd
import pytest

from slk import ltf_discovery, trend_study
from slk.ltf_features import features

EX = os.path.join(os.path.dirname(__file__), "..", "data", "examples")


def _H(rows):
    t = np.array([np.datetime64("2024-01-01T00:00") + np.timedelta64(i, "h") for i in range(len(rows))], dtype="datetime64[ns]")
    a = np.array(rows, float)
    return {"t": t, "open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3]}


def test_path_sell_hits_2R_before_stop():
    # entry 1.1000 at the close of candle 0, stop 1.1010 (10 pips), 2R = 1.0980
    H = _H([[1.1, 1.1, 1.1, 1.1], [1.1, 1.1005, 1.0990, 1.0992], [1.0992, 1.0995, 1.0979, 1.098], [1.098, 1.1011, 1.098, 1.1]])
    r = trend_study.path(H, 0, "SELL", 1.1, 1.101, None, 0.0001)
    assert r["win_1R"] and r["win_2R"] and not r["win_3R"]
    assert r["R_2R"] == pytest.approx(2 - 0.12, abs=1e-3)
    assert r["R_3R"] == pytest.approx(-1 - 0.12, abs=1e-3)  # stopped on candle 3


def test_same_candle_stop_and_target_is_a_loss():
    H = _H([[1.1, 1.1, 1.1, 1.1], [1.1, 1.1011, 1.0970, 1.098]])
    r = trend_study.path(H, 0, "SELL", 1.1, 1.101, None, 0.0001)
    assert r["stopped"] and not r["win_1R"]


def test_limit_fill_candle_can_only_stop_out():
    H = _H([[1.099, 1.1012, 1.0950, 1.096], [1.096, 1.097, 1.09, 1.091]])
    r = trend_study.path_limit(H, 0, "SELL", 1.1, 1.101, None, 0.0001)
    assert r["stopped"] and r["R_5R"] < -1


def test_features_use_no_future_candles():
    rng = np.random.default_rng(1)
    c = 1.1 + np.cumsum(rng.normal(0, 0.0005, 80))
    rows = [[x, x + 0.0004, x - 0.0004, x + rng.normal(0, 0.0002)] for x in c]
    H = _H(rows)
    f1 = features(H, 50, "SELL", float(H["close"][50]), float(H["close"][50]) + 0.001, 40, 0.0001)
    H2 = {k: v.copy() for k, v in H.items()}
    for k in ("open", "high", "low", "close"):
        H2[k][51:] = H2[k][51:] * 1.05  # change the future
    f2 = features(H2, 50, "SELL", float(H["close"][50]), float(H["close"][50]) + 0.001, 40, 0.0001)
    assert f1 == f2


def test_discovery_finds_a_planted_condition_and_rejects_noise():
    rng = np.random.default_rng(0)
    n = 4000
    df = pd.DataFrame({"tf": "H2", "entry": "h1_confirm", "pair": "EURUSD",
                       "year": rng.choice([2019, 2020, 2021, 2023, 2024], n),
                       "sweep": rng.random(n) < 0.3, "fvg": rng.random(n) < 0.5})
    df["R_3R"] = np.where(df["sweep"], 0.4, -0.2) + rng.normal(0, 0.5, n)
    single, _ = ltf_discovery.screen(df, 2023)
    held = set(single[single["holds"]]["rule"])
    assert "sweep=yes" in held
    assert not ({"fvg=yes", "fvg=no"} & held)


def test_daily_state():
    st = [{"side": "SELL", "confirm_time": "2024-01-02 00:00", "end_time": "2024-01-05 00:00", "kevin_outcome": "target"}]
    t = np.datetime64("2024-01-03T00:00", "ns")
    assert trend_study.daily_state(st, "SELL", t) == "same"
    assert trend_study.daily_state(st, "BUY", t) == "opposite"
    assert trend_study.daily_state(st, "SELL", np.datetime64("2024-01-06T00:00", "ns")) == "same_target_hit"
    assert trend_study.daily_state(st, "SELL", np.datetime64("2024-01-01T00:00", "ns")) == "none"


@pytest.mark.skipif(not os.path.exists(os.path.join(EX, "EURAUD_H1.csv.gz")), reason="example candles missing")
def test_h4_story_sees_kevin_euraud_level():
    """Kevin's EURAUD H4 sell 17 Feb 2026 (entry 1.6748): an H4 story on his side within 10 pips of his entry."""
    from slk.story import find_stories
    h1 = pd.read_csv(os.path.join(EX, "EURAUD_H1.csv.gz"), parse_dates=["t"], index_col="t")
    st = [s for s in find_stories("EURAUD", h1, "H4") if s["side"] == "SELL"
          and "2026-02-14" <= s["confirm_time"] <= "2026-02-20 23:59"]
    assert st and min(abs(float(s["level"]) - 1.6748) for s in st) < 0.0010
