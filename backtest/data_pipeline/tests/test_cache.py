import os

import pandas as pd
import pytest

from .. import cache as cache_module


def row(t, o, h, l, c, v=100):
    return {"time": t, "open": o, "high": h, "low": l, "close": c, "volume": v}


@pytest.fixture(autouse=True)
def isolated_data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))


def test_append_then_load_round_trips():
    cache_module.append("dukascopy", "EURUSD", "H1", [row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105)])
    df = cache_module.load("dukascopy", "EURUSD", "H1")
    assert len(df) == 1
    assert df.iloc[0]["close"] == 1.105


def test_append_merges_and_dedupes_by_time():
    cache_module.append("dukascopy", "EURUSD", "H1", [row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105)])
    cache_module.append("dukascopy", "EURUSD", "H1", [
        row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.999),  # same time -- existing row wins (kept first)
        row("2024-01-01T01:00:00Z", 1.105, 1.115, 1.10, 1.11),
    ])
    df = cache_module.load("dukascopy", "EURUSD", "H1")
    assert len(df) == 2
    assert df.iloc[0]["close"] == 1.105  # de-dup kept the already-cached row, not the resubmitted one


def test_append_leaves_the_original_file_untouched_if_the_write_fails(monkeypatch):
    # Confirmed live: two bot processes calling append() concurrently for
    # the same file crashed a running bot with pandas.errors.EmptyDataError
    # -- a plain to_csv(path) truncates the file in place, so a concurrent
    # reader can catch it mid-write and see it as empty. Writing to a temp
    # file and os.replace()-ing it into place must mean a failed write
    # never touches the real file at all.
    cache_module.append("dukascopy", "EURUSD", "H1", [row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105)])
    path = cache_module.cache_path("dukascopy", "EURUSD", "H1")
    original_content = open(path).read()

    def boom(self, *a, **k):
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(pd.DataFrame, "to_csv", boom)
    with pytest.raises(RuntimeError):
        cache_module.append("dukascopy", "EURUSD", "H1", [row("2024-01-01T02:00:00Z", 1.11, 1.12, 1.10, 1.115)])

    assert open(path).read() == original_content  # untouched, not truncated/corrupted
    tmp_leftovers = [f for f in os.listdir(os.path.dirname(path)) if f.endswith(".tmp")]
    assert tmp_leftovers == []  # the failed temp file was cleaned up, not left behind


def test_append_writes_are_never_observed_as_empty_by_a_concurrent_reader(monkeypatch):
    # Same scenario as above, from the READER's side: even mid-append, a
    # concurrent pd.read_csv() on the same path must see a complete file
    # (old or new), never a truncated/empty one -- proven by hooking
    # os.replace() (the atomic swap) and checking the file is fully
    # readable immediately beforehand and immediately after.
    cache_module.append("dukascopy", "EURUSD", "H1", [row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105)])
    path = cache_module.cache_path("dukascopy", "EURUSD", "H1")

    real_replace = os.replace
    seen_readable_before_swap = []

    def spy_replace(src, dst):
        # The real (old) file at `dst` must still be fully intact right up
        # until the atomic swap itself -- never truncated in advance.
        seen_readable_before_swap.append(pd.read_csv(dst).to_dict())
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy_replace)
    cache_module.append("dukascopy", "EURUSD", "H1", [row("2024-01-01T01:00:00Z", 1.105, 1.115, 1.10, 1.11)])

    assert len(seen_readable_before_swap) == 1
    assert seen_readable_before_swap[0] != {}  # old file was still fully readable, not pre-truncated
