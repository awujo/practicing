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


# ---------------------------------------------------------------------------
# REPAIRABLE_GRANULARITIES -- deriving H4/D/W from H1.
#
# These exist to repair a cache whose H4/D/W tail was polluted by MT5
# bars on a different anchor (2026-08; see resample.py's own note). The
# whole point is that the derived series lands on ONE grid -- the same
# grid the clean Dukascopy history uses -- so these tests pin the
# anchoring, not just the aggregation.
# ---------------------------------------------------------------------------

def _hourly(start, hours, **overrides):
    idx = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    data = {"time": idx, "open": 1.0, "high": 1.1, "low": 0.9,
            "close": 1.05, "volume": 1.0}
    data.update(overrides)
    return pd.DataFrame(data)


def test_h4_lands_on_the_clean_utc_grid():
    from ..resample import REPAIRABLE_GRANULARITIES, resample_ohlcv
    _src, rule, kw = REPAIRABLE_GRANULARITIES["H4"]
    out = resample_ohlcv(_hourly("2026-08-03", 24 * 14), rule, **kw)
    assert sorted(out.time.dt.hour.unique()) == [0, 4, 8, 12, 16, 20]


def test_daily_lands_on_midnight():
    from ..resample import REPAIRABLE_GRANULARITIES, resample_ohlcv
    _src, rule, kw = REPAIRABLE_GRANULARITIES["D"]
    out = resample_ohlcv(_hourly("2026-08-03", 24 * 14), rule, **kw)
    assert sorted(out.time.dt.hour.unique()) == [0]


def test_weekly_opens_on_monday_midnight():
    """Dukascopy's weekly bars are stamped on Mondays at 00:00 -- GBPUSD
    W starts 2003-04-28, a Monday, every row at hour 0. A derived weekly
    series that labelled the closing Sunday instead would silently shift
    every weekly bias decision by a week."""
    from ..resample import REPAIRABLE_GRANULARITIES, resample_ohlcv
    _src, rule, kw = REPAIRABLE_GRANULARITIES["W"]
    out = resample_ohlcv(_hourly("2026-08-03", 24 * 21), rule, **kw)
    assert sorted(out.time.dt.hour.unique()) == [0]
    assert sorted(out.time.dt.dayofweek.unique()) == [0]  # Monday


def test_a_bar_is_stamped_when_it_opened_not_when_it_closed():
    from ..resample import REPAIRABLE_GRANULARITIES, resample_ohlcv
    df = _hourly("2026-08-03", 8)
    _src, rule, kw = REPAIRABLE_GRANULARITIES["H4"]
    out = resample_ohlcv(df, rule, **kw)
    assert out.time.iloc[0] == pd.Timestamp("2026-08-03 00:00", tz="UTC")


def test_ohlc_aggregates_across_the_whole_bin():
    from ..resample import REPAIRABLE_GRANULARITIES, resample_ohlcv
    df = _hourly("2026-08-03", 4,
                 open=[1.0, 2.0, 3.0, 4.0], high=[1.5, 9.0, 3.5, 4.5],
                 low=[0.5, 1.5, 0.1, 3.5], close=[1.2, 2.2, 3.2, 4.2],
                 volume=[1.0, 2.0, 3.0, 4.0])
    _src, rule, kw = REPAIRABLE_GRANULARITIES["H4"]
    out = resample_ohlcv(df, rule, **kw)
    assert len(out) == 1
    row = out.iloc[0]
    assert row.open == 1.0 and row.close == 4.2
    assert row.high == 9.0 and row.low == 0.1
    assert row.volume == 10.0


def test_deriving_never_reproduces_the_broken_multi_grid_shape():
    """The bug's signature was H4 bars on 24 distinct hours. A derived
    series cannot do that by construction -- this pins that it doesn't,
    even across a weekend gap where bins go empty."""
    from ..resample import REPAIRABLE_GRANULARITIES, resample_ohlcv
    df = _hourly("2026-08-03", 24 * 14)
    df = df[~df.time.dt.dayofweek.isin([5, 6])]  # drop the weekend
    _src, rule, kw = REPAIRABLE_GRANULARITIES["H4"]
    out = resample_ohlcv(df, rule, **kw)
    assert len(sorted(out.time.dt.hour.unique())) == 6
    gaps = out.time.diff().dropna().dt.total_seconds() / 3600
    assert (gaps >= 4).all(), "no derived bar may sit closer than one bar to the previous"


def test_repairable_and_derived_granularities_do_not_overlap():
    """H4/D/W are fetched natively. If they ever appeared in
    DERIVED_GRANULARITIES, derive_granularities.py --all would silently
    overwrite a fetched series with a computed one."""
    from ..resample import DERIVED_GRANULARITIES, REPAIRABLE_GRANULARITIES
    assert not set(DERIVED_GRANULARITIES) & set(REPAIRABLE_GRANULARITIES)
