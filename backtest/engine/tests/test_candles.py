"""Tests for candles.py's in-process cache.

Motivation (2026-09-11, from a live profile): load_candles() was 29% of a
single run_backtest() call's cost on the production VPS -- 34.5s of
54-73s -- entirely spent re-reading and re-parsing a cache file that
usually had not changed since the previous call seconds earlier. These
tests are about the CACHING behavior specifically: that it actually skips
re-parsing when nothing changed, that it correctly detects when something
did change, and that callers can never see each other's mutations through
a shared cache entry. Correctness of the parsed VALUES is already covered
by every existing run_backtest()-level test -- if caching introduced a
bug there, those would catch it; the full suite passing after this change
is part of this fix's own verification.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from .. import candles as candles_module
from ..candles import Candle, load_candles
from ...data_pipeline import cache as cache_module


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))
    # The module-level cache is keyed by absolute path, and DATA_ROOT
    # changes per test, so stale entries from another test can never be
    # served here -- but clear it anyway so call-COUNT assertions below
    # start from zero rather than depending on test execution order.
    candles_module._cache.clear()
    yield
    candles_module._cache.clear()


def _write_rows(path, rows):
    import os
    os.makedirs(path.parent, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


def _cache_file(source="dukascopy", symbol="EURUSD", granularity="H1"):
    from pathlib import Path
    return Path(cache_module.cache_path(source, symbol, granularity))


def _row(t, o=1.1, h=1.2, l=1.0, c=1.15, v=100.0):
    return {"time": t, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_loads_real_candles_correctly():
    path = _cache_file()
    _write_rows(path, [_row("2026-01-01T00:00:00Z"), _row("2026-01-01T01:00:00Z")])
    result = load_candles("dukascopy", "EURUSD", "H1")
    assert len(result) == 2
    assert all(isinstance(c, Candle) for c in result)
    assert result[0].time < result[1].time


def test_second_call_with_no_change_does_not_reparse():
    path = _cache_file()
    _write_rows(path, [_row("2026-01-01T00:00:00Z")])
    load_candles("dukascopy", "EURUSD", "H1")

    with patch.object(cache_module, "load", wraps=cache_module.load) as spy:
        result = load_candles("dukascopy", "EURUSD", "H1")

    spy.assert_not_called()
    assert len(result) == 1


def test_change_to_the_file_is_picked_up():
    """The whole point: a real update must never be missed just because
    caching exists."""
    path = _cache_file()
    _write_rows(path, [_row("2026-01-01T00:00:00Z")])
    first = load_candles("dukascopy", "EURUSD", "H1")
    assert len(first) == 1

    _write_rows(path, [_row("2026-01-01T00:00:00Z"), _row("2026-01-01T01:00:00Z")])
    # Force a distinct mtime even on filesystems with coarse timestamp
    # resolution, so this test can't pass by accident of timing.
    import os, time
    os.utime(path, (time.time() + 5, time.time() + 5))

    second = load_candles("dukascopy", "EURUSD", "H1")
    assert len(second) == 2


def test_missing_file_raises_the_same_error_as_before():
    with pytest.raises(FileNotFoundError):
        load_candles("dukascopy", "NOPE", "H1")


def test_returned_list_is_independent_between_calls():
    """A caller mutating what it got back (sorting in place, appending)
    must never corrupt what the NEXT caller sees from the same cache
    entry -- this is the one correctness risk caching introduces that
    the previous always-fresh-list behavior could never have had."""
    path = _cache_file()
    _write_rows(path, [_row("2026-01-01T00:00:00Z"), _row("2026-01-01T01:00:00Z")])
    first = load_candles("dukascopy", "EURUSD", "H1")
    first.append("not a candle")
    first.clear()

    second = load_candles("dukascopy", "EURUSD", "H1")
    assert len(second) == 2
    assert all(isinstance(c, Candle) for c in second)


def test_different_granularities_of_the_same_symbol_do_not_collide():
    h1_path = _cache_file(granularity="H1")
    d_path = _cache_file(granularity="D")
    _write_rows(h1_path, [_row("2026-01-01T00:00:00Z")])
    _write_rows(d_path, [_row("2026-01-01T00:00:00Z"), _row("2026-01-02T00:00:00Z")])

    assert len(load_candles("dukascopy", "EURUSD", "H1")) == 1
    assert len(load_candles("dukascopy", "EURUSD", "D")) == 2


# ---- off-boundary H4/D/W rows are dropped ----
# Confirmed live 2026-09-15: every one of 25+ instruments' D/W/H4 cache
# files carries a consistent block of rows that don't land on a valid
# UTC boundary (H4 at 05:00/07:00/... instead of 04:00/08:00/...),
# traced to dukascopy-python's own upstream resampling for a shared
# historical stretch. Feeding these into structure/bias detection (which
# assumes valid boundaries throughout) produced visibly unstable output:
# JP225's H4 bias flipped bullish/bearish twice within 30 seconds on the
# same running process, with no real H4 candle having closed in between.

def test_h4_candles_off_the_00_04_08_12_16_20_grid_are_dropped():
    path = _cache_file(granularity="H4")
    _write_rows(path, [
        _row("2026-01-01T00:00:00Z"), _row("2026-01-01T05:00:00Z"),  # bad -- not on the grid
        _row("2026-01-01T04:00:00Z"), _row("2026-01-01T08:00:00Z"),
    ])
    result = load_candles("dukascopy", "EURUSD", "H4")
    assert [c.time.hour for c in result] == [0, 4, 8]


def test_daily_candles_off_midnight_utc_are_dropped():
    path = _cache_file(granularity="D")
    _write_rows(path, [_row("2026-01-01T00:00:00Z"), _row("2026-01-02T03:00:00Z")])  # bad
    result = load_candles("dukascopy", "EURUSD", "D")
    assert len(result) == 1
    assert result[0].time.hour == 0


def test_weekly_candles_off_monday_midnight_are_dropped():
    path = _cache_file(granularity="W")
    _write_rows(path, [
        _row("2026-01-05T00:00:00Z"),  # a Monday -- valid
        _row("2026-01-06T00:00:00Z"),  # a Tuesday -- bad weekday
        _row("2026-01-12T03:00:00Z"),  # a Monday but bad hour
    ])
    result = load_candles("dukascopy", "EURUSD", "W")
    assert len(result) == 1
    assert result[0].time.day == 5


def test_h1_candles_have_no_boundary_restriction():
    """H1 has no fixed-boundary concept -- any hour is a valid open."""
    path = _cache_file(granularity="H1")
    _write_rows(path, [_row("2026-01-01T05:00:00Z"), _row("2026-01-01T07:00:00Z")])
    result = load_candles("dukascopy", "EURUSD", "H1")
    assert len(result) == 2
