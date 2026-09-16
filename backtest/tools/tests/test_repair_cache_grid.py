"""Tests for the H4/D/W cache repair.

This one writes destructively to real cache files when --apply is
passed, so the tests build an actual poisoned cache on disk -- clean
UTC-anchored history, then MT5-anchored bars spliced into the tail
exactly as live_cache_sync.py did -- and check the repair restores it.
Asserting on hand-built expectations alone would not prove much; the
point is that the real damage shape is detected and removed.
"""

import pandas as pd
import pytest

from ...data_pipeline import cache as cache_module
from ..repair_cache_grid import inspect, rebuild, _off_grid, _overlapping


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))
    yield


SRC = "dukascopy"
SYM = "TESTPAIR"


def _rows(times, price=1.0):
    return [{"time": t.isoformat().replace("+00:00", "Z"),
             "open": price, "high": price + 0.1, "low": price - 0.1,
             "close": price, "volume": 1.0}
            for t in times]


def _write(granularity, times, price=1.0):
    cache_module.append(SRC, SYM, granularity, _rows(times, price))


def _seed_h1(start="2026-07-20", days=40):
    """H1 is the source of truth for the rebuild -- undamaged, every hour."""
    idx = pd.date_range(start, periods=24 * days, freq="h", tz="UTC")
    _write("H1", idx)


def test_clean_series_is_reported_clean():
    _seed_h1()
    _write("H4", pd.date_range("2026-07-20", periods=60, freq="4h", tz="UTC"))
    before = inspect(SRC, SYM, "H4")
    assert before["off_grid"] == 0
    assert before["overlapping"] == 0


def test_the_real_damage_shape_is_detected():
    """Clean UTC-anchored bars, then MT5-anchored bars spliced in -- the
    01/05/09/13/17/21 grid live_cache_sync.py was appending."""
    _seed_h1()
    # The two grids must COVER THE SAME DAYS, which is what actually
    # happened: Dukascopy kept supplying 00/04/08 bars while the live
    # sync appended MT5's 01/05/09 bars for the same period.
    clean = pd.date_range("2026-07-20", periods=160, freq="4h", tz="UTC")
    poisoned = pd.date_range("2026-08-10 01:00", periods=24, freq="4h", tz="UTC")
    _write("H4", clean)
    _write("H4", poisoned)

    before = inspect(SRC, SYM, "H4")
    assert before["off_grid"] == 24
    assert before["overlapping"] > 0, "interleaved grids must show as sub-bar gaps"
    assert before["first_bad"] == pd.Timestamp("2026-08-10 01:00", tz="UTC")
    # The signature that made this visible at all: more than 6 distinct hours.
    assert len(before["hours"]) > 6


def test_repair_removes_the_foreign_bars_and_restores_the_grid():
    _seed_h1()
    _write("H4", pd.date_range("2026-07-20", periods=160, freq="4h", tz="UTC"))
    _write("H4", pd.date_range("2026-08-10 01:00", periods=24, freq="4h", tz="UTC"))
    before = inspect(SRC, SYM, "H4")
    assert before["off_grid"] == 24 and before["overlapping"] > 0

    rebuild(SRC, SYM, "H4", "2026-08-01T00:00:00Z", apply=True)

    after = inspect(SRC, SYM, "H4")
    assert after["off_grid"] == 0
    assert after["overlapping"] == 0
    assert after["hours"] == [0, 4, 8, 12, 16, 20]


def test_history_before_the_cutoff_is_never_touched():
    """The clean twenty years are the thing most worth not breaking."""
    _seed_h1()
    clean = pd.date_range("2026-07-20", periods=160, freq="4h", tz="UTC")
    _write("H4", clean, price=1.5)
    _write("H4", pd.date_range("2026-08-10 01:00", periods=24, freq="4h", tz="UTC"), price=9.9)

    kept = cache_module.load(SRC, SYM, "H4")
    kept_before = kept[pd.to_datetime(kept.time, utc=True) < pd.Timestamp("2026-08-01", tz="UTC")]
    original = kept_before.copy()

    rebuild(SRC, SYM, "H4", "2026-08-01T00:00:00Z", apply=True)

    now = cache_module.load(SRC, SYM, "H4")
    now_before = now[pd.to_datetime(now.time, utc=True) < pd.Timestamp("2026-08-01", tz="UTC")]
    pd.testing.assert_frame_equal(
        original.reset_index(drop=True), now_before.reset_index(drop=True))
    assert (now_before["close"] == 1.5).all()


def test_dry_run_writes_nothing():
    _seed_h1()
    _write("H4", pd.date_range("2026-08-10 01:00", periods=24, freq="4h", tz="UTC"))
    before = cache_module.load(SRC, SYM, "H4")

    result = rebuild(SRC, SYM, "H4", "2026-08-01T00:00:00Z", apply=False)

    assert "would_write" in result and result["would_write"] > 0
    pd.testing.assert_frame_equal(before, cache_module.load(SRC, SYM, "H4"))


def test_rebuilt_bars_aggregate_the_real_h1_data():
    """A rebuild that produced correctly-timed but wrong-priced bars
    would pass every grid check and still be useless."""
    idx = pd.date_range("2026-07-28", periods=24 * 10, freq="h", tz="UTC")
    rows = [{"time": t.isoformat().replace("+00:00", "Z"),
             "open": 10.0 + i, "high": 20.0 + i, "low": 5.0 + i,
             "close": 15.0 + i, "volume": 2.0}
            for i, t in enumerate(idx)]
    cache_module.append(SRC, SYM, "H1", rows)
    _write("H4", pd.date_range("2026-08-05 01:00", periods=6, freq="4h", tz="UTC"))

    rebuild(SRC, SYM, "H4", "2026-08-01T00:00:00Z", apply=True)

    h4 = cache_module.load(SRC, SYM, "H4")
    h4["time"] = pd.to_datetime(h4["time"], utc=True)
    h1 = cache_module.load(SRC, SYM, "H1")
    h1["time"] = pd.to_datetime(h1["time"], utc=True)

    bar = h4[h4["time"] == pd.Timestamp("2026-08-05 04:00", tz="UTC")].iloc[0]
    members = h1[(h1["time"] >= pd.Timestamp("2026-08-05 04:00", tz="UTC"))
                 & (h1["time"] < pd.Timestamp("2026-08-05 08:00", tz="UTC"))]
    assert len(members) == 4
    assert bar["open"] == members["open"].iloc[0]
    assert bar["close"] == members["close"].iloc[-1]
    assert bar["high"] == members["high"].max()
    assert bar["low"] == members["low"].min()
    assert bar["volume"] == members["volume"].sum()


def test_daily_and_weekly_repair_to_their_own_grids():
    _seed_h1(start="2026-07-06", days=60)
    _write("D", pd.date_range("2026-08-10 21:00", periods=10, freq="D", tz="UTC"))
    _write("W", pd.date_range("2026-08-08 21:00", periods=3, freq="7D", tz="UTC"))

    rebuild(SRC, SYM, "D", "2026-08-01T00:00:00Z", apply=True)
    rebuild(SRC, SYM, "W", "2026-08-01T00:00:00Z", apply=True)

    d = inspect(SRC, SYM, "D")
    assert d["off_grid"] == 0 and d["hours"] == [0]
    w = inspect(SRC, SYM, "W")
    assert w["off_grid"] == 0 and w["hours"] == [0]
    wt = pd.to_datetime(cache_module.load(SRC, SYM, "W")["time"], utc=True)
    assert sorted(wt.dt.dayofweek.unique()) == [0]  # Monday


def test_weekly_detects_a_saturday_anchored_bar_as_off_grid():
    """MT5's weekly bars open Saturday 21:00 UTC. On the hour check
    alone a Saturday 00:00 bar would look fine, so the day-of-week half
    of the grid check has to be doing work."""
    t = pd.Series(pd.to_datetime(["2026-08-08 00:00", "2026-08-10 00:00"], utc=True))
    bad = _off_grid(t, "W")
    assert bad.tolist() == [True, False]  # Saturday rejected, Monday kept


def test_overlapping_counts_only_sub_bar_gaps():
    ok = pd.Series(pd.to_datetime(
        ["2026-08-10 00:00", "2026-08-10 04:00", "2026-08-10 08:00"], utc=True))
    assert _overlapping(ok, "H4") == 0
    bad = pd.Series(pd.to_datetime(
        ["2026-08-10 00:00", "2026-08-10 01:00", "2026-08-10 04:00"], utc=True))
    assert _overlapping(bad, "H4") == 2
