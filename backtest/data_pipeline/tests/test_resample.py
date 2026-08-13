import pandas as pd
import pytest

from ..resample import resample_ohlcv


def h1_row(hour, o, h, l, c, v=100):
    return {
        "time": pd.Timestamp("2024-01-01T00:00:00Z") + pd.Timedelta(hours=hour),
        "open": o, "high": h, "low": l, "close": c, "volume": v,
    }


def test_h1_to_h2_aggregates_ohlcv_correctly():
    # Two H1 bars (hours 0 and 1) should merge into one H2 bar (00:00-02:00):
    # open = first bar's open, close = second bar's close, high/low = extremes, volume = sum.
    df = pd.DataFrame([
        h1_row(0, 1.1000, 1.1020, 1.0990, 1.1010, v=100),
        h1_row(1, 1.1010, 1.1030, 1.1005, 1.1025, v=150),
    ])

    out = resample_ohlcv(df, "2h")

    assert len(out) == 1
    row = out.iloc[0]
    assert row["open"] == pytest.approx(1.1000)
    assert row["high"] == pytest.approx(1.1030)
    assert row["low"] == pytest.approx(1.0990)
    assert row["close"] == pytest.approx(1.1025)
    assert row["volume"] == pytest.approx(250)
    assert row["time"] == pd.Timestamp("2024-01-01T00:00:00Z")


def test_h1_to_h3_bins_align_to_utc_midnight():
    # Hours 0,1,2 -> one H3 bar; hour 3 starts a new H3 bar.
    df = pd.DataFrame([h1_row(h, 1.10, 1.11, 1.09, 1.105) for h in range(4)])

    out = resample_ohlcv(df, "3h")

    assert len(out) == 2
    assert out.iloc[0]["time"] == pd.Timestamp("2024-01-01T00:00:00Z")
    assert out.iloc[1]["time"] == pd.Timestamp("2024-01-01T03:00:00Z")


def test_m15_to_m45_tiles_exactly_with_no_remainder():
    # 1440 minutes / 45 = 32 exactly -- three M15 bars (0, 15, 30 min) -> one M45 bar.
    base = pd.Timestamp("2024-01-01T00:00:00Z")
    df = pd.DataFrame([
        {"time": base, "open": 1.10, "high": 1.101, "low": 1.099, "close": 1.1005, "volume": 10},
        {"time": base + pd.Timedelta(minutes=15), "open": 1.1005, "high": 1.102, "low": 1.100, "close": 1.101, "volume": 10},
        {"time": base + pd.Timedelta(minutes=30), "open": 1.101, "high": 1.103, "low": 1.1008, "close": 1.1025, "volume": 10},
    ])

    out = resample_ohlcv(df, "45min")

    assert len(out) == 1
    row = out.iloc[0]
    assert row["open"] == pytest.approx(1.10)
    assert row["close"] == pytest.approx(1.1025)
    assert row["high"] == pytest.approx(1.103)
    assert row["volume"] == pytest.approx(30)


def test_gap_produces_no_synthetic_candle():
    """A weekend/feed gap should just produce no output row for the empty bin, not a flat candle."""
    df = pd.DataFrame([
        h1_row(0, 1.10, 1.11, 1.09, 1.105),
        # hours 1-9 missing entirely (simulating a gap)
        h1_row(10, 1.20, 1.21, 1.19, 1.205),
    ])

    out = resample_ohlcv(df, "2h")

    # Bar 0 (hours 0-2) present, bars for hours 2-10 absent, bar for hour 10-12 present.
    times = list(out["time"])
    assert pd.Timestamp("2024-01-01T00:00:00Z") in times
    assert pd.Timestamp("2024-01-01T10:00:00Z") in times
    assert len(out) == 2  # not 6 -- the empty bins in between are dropped, not filled
