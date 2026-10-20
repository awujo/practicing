import os

import pandas as pd
import pytest

from slk import leg_backtest as L

CSV = "data/debug/GBPJPY_H1_ctrader.csv.gz"


def test_walk_stop_first_and_cost():
    t = pd.date_range("2026-01-05", periods=3, freq="h").to_numpy()
    H = {"t": t, "open": [1.0, 1.0, 1.0], "high": [1.02, 1.0, 1.0], "low": [0.98, 1.0, 1.0], "close": [1.0] * 3}
    w = L.walk(H, t[0], "SELL", 1.0, 1.01, 0.99, 0.01, 0.0)
    assert w["outcome"] == "loss" and w["R"] == pytest.approx(-1.0)  # both touched in one hour: stop first


@pytest.mark.skipif(not os.path.exists(CSV), reason="local debug candles")
def test_pair_trades_runs():
    h1 = pd.read_csv(CSV, parse_dates=["t"], index_col="t")
    h1 = h1[h1.index < "2024-01-01"]
    df = pd.DataFrame(L.pair_trades("GBPJPY", h1))
    assert {"confirmation", "after target, 1st break"} <= set(df["kind"])
    assert (df["risk_pips"] > 0).all() and set(df["outcome"]) <= {"win", "loss", "timeout"}
