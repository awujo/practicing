"""
Reading the end of the cache without parsing all of it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from .. import cache


def write(tmp_path, rows, symbol="EURUSD", granularity="H1"):
    cache.DATA_ROOT = str(tmp_path)
    T0 = pd.Timestamp("2020-01-01")
    cache.append("dukascopy", symbol, granularity, [
        {"time": (T0 + pd.Timedelta(hours=i)).isoformat(), "open": 1.1 + i * 1e-5,
         "high": 1.2, "low": 1.0, "close": 1.1, "volume": i}
        for i in range(rows)])


def test_the_tail_is_the_last_n_rows_and_they_are_the_right_ones(tmp_path,
                                                                 monkeypatch):
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))
    write(tmp_path, 5000)

    whole = cache.load("dukascopy", "EURUSD", "H1")
    tail = cache.load_tail("dukascopy", "EURUSD", "H1", 100)

    assert len(tail) == 100
    assert tail["time"].iloc[-1] == whole["time"].iloc[-1], "same last candle"
    assert tail["time"].iloc[0] == whole["time"].iloc[-100]
    pd.testing.assert_frame_equal(
        tail.reset_index(drop=True),
        whole.tail(100).reset_index(drop=True), check_dtype=False)


def test_it_never_returns_a_partial_first_row(tmp_path, monkeypatch):
    """Seeking to a byte offset lands mid-line. A half-parsed row would
    be a candle with a truncated timestamp, which is worse than slow."""
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))
    write(tmp_path, 3000)

    for rows in (1, 2, 7, 31, 100, 999):
        tail = cache.load_tail("dukascopy", "EURUSD", "H1", rows)
        assert len(tail) == rows
        assert tail["time"].notna().all(), f"a broken row at rows={rows}"
        assert tail["open"].notna().all()


def test_asking_for_more_than_exists_returns_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))
    write(tmp_path, 50)

    tail = cache.load_tail("dukascopy", "EURUSD", "H1", 5000)
    assert len(tail) == 50
    pd.testing.assert_frame_equal(
        tail, cache.load("dukascopy", "EURUSD", "H1"), check_dtype=False)


def test_zero_or_negative_rows_falls_back_to_the_whole_file(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))
    write(tmp_path, 40)
    assert len(cache.load_tail("dukascopy", "EURUSD", "H1", 0)) == 40


def test_a_missing_file_still_raises_the_same_error(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        cache.load_tail("dukascopy", "NOSUCH", "H1", 10)


def test_the_tail_matches_a_full_load_at_every_size(tmp_path, monkeypatch):
    """The property that matters: this is an optimisation, so it must
    return exactly what the slow path would."""
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))
    write(tmp_path, 1500)
    whole = cache.load("dukascopy", "EURUSD", "H1")

    for rows in (1, 3, 64, 500, 1499, 1500, 1501):
        tail = cache.load_tail("dukascopy", "EURUSD", "H1", rows)
        expected = whole.tail(min(rows, len(whole))).reset_index(drop=True)
        pd.testing.assert_frame_equal(tail.reset_index(drop=True), expected,
                                       check_dtype=False)
