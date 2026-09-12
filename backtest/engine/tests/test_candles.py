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
