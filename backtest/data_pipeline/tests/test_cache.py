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
        # An out-of-order row forces the full merge path, which is the
        # one that rewrites the file and so is the one at risk here.
        cache_module.append("dukascopy", "EURUSD", "H1", [
            row("2023-06-01T00:00:00Z", 1.11, 1.12, 1.10, 1.115),
        ])

    assert open(path).read() == original_content  # untouched, not truncated/corrupted
    tmp_leftovers = [f for f in os.listdir(os.path.dirname(path)) if f.endswith(".tmp")]
    assert tmp_leftovers == []  # the failed temp file was cleaned up, not left behind


# ---- the append-only fast path ----

def test_appending_newer_rows_does_not_rewrite_the_whole_file(monkeypatch):
    # The point of the fast path. Measured on the live VPS, the full
    # read-merge-rewrite cost 36.4s to add 10 candles to a 9.4MB H1 file
    # -- per granularity, per instrument, per sync, on two bots. Adding
    # rows that all sort after what's cached must touch neither
    # pd.read_csv nor to_csv.
    cache_module.append("dukascopy", "EURUSD", "H1", [row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105)])

    def fail(*a, **k):
        raise AssertionError("fast path must not read or rewrite the whole file")

    monkeypatch.setattr(pd, "read_csv", fail)
    monkeypatch.setattr(pd.DataFrame, "to_csv", fail)
    added = cache_module.append("dukascopy", "EURUSD", "H1",
                                 [row("2024-01-01T01:00:00Z", 1.105, 1.115, 1.10, 1.11)])
    assert added == 1


def test_resubmitting_only_already_cached_rows_does_no_work_at_all(monkeypatch):
    # The usual live case: sync fetches the last 10 candles, of which
    # nine are already on disk and none are new. That must be free.
    rows = [row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105),
            row("2024-01-01T01:00:00Z", 1.105, 1.115, 1.10, 1.11)]
    cache_module.append("dukascopy", "EURUSD", "H1", rows)

    def fail(*a, **k):
        raise AssertionError("re-submitting known rows must not touch the file")

    monkeypatch.setattr(pd, "read_csv", fail)
    monkeypatch.setattr(pd.DataFrame, "to_csv", fail)
    assert cache_module.append("dukascopy", "EURUSD", "H1", rows) == 0


def test_fast_path_and_full_merge_produce_identical_files(tmp_path, monkeypatch):
    # The property that makes the fast path safe to ship: for input it
    # accepts, it must leave the file byte-for-byte identical to what the
    # original full merge would have produced.
    seed = [row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105)]
    later = [row("2024-01-01T01:00:00Z", 1.105, 1.115, 1.10, 1.11),
             row("2024-01-01T02:00:00Z", 1.11, 1.12, 1.105, 1.115)]

    cache_module.append("dukascopy", "FAST", "H1", seed)
    cache_module.append("dukascopy", "FAST", "H1", later)
    fast = open(cache_module.cache_path("dukascopy", "FAST", "H1")).read()

    cache_module.append("dukascopy", "SLOW", "H1", seed)
    slow_path = cache_module.cache_path("dukascopy", "SLOW", "H1")
    cache_module._merge_rewrite(slow_path, later)
    slow = open(slow_path).read()

    assert fast == slow


def test_out_of_order_rows_fall_back_to_the_full_merge():
    # A backfill that interleaves with cached data can't just be appended
    # -- it must still come out deduped and sorted.
    cache_module.append("dukascopy", "EURUSD", "H1", [
        row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105),
        row("2024-01-01T05:00:00Z", 1.13, 1.14, 1.12, 1.135),
    ])
    cache_module.append("dukascopy", "EURUSD", "H1", [
        row("2024-01-01T03:00:00Z", 1.11, 1.12, 1.10, 1.115),  # slots in between
        row("2024-01-01T05:00:00Z", 1.99, 1.99, 1.99, 1.999),  # duplicate time
    ])
    df = cache_module.load("dukascopy", "EURUSD", "H1")
    times = [str(t) for t in df["time"]]
    assert times == sorted(times)
    assert len(times) == len(set(times))
    assert len(df) == 3
    assert df.iloc[2]["close"] == 1.135  # existing row won the de-dup, as before


def test_a_header_only_file_falls_back_rather_than_appending_blindly():
    path = cache_module.cache_path("dukascopy", "EURUSD", "H1")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(",".join(cache_module.COLUMNS) + "\n")

    cache_module.append("dukascopy", "EURUSD", "H1", [row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105)])
    df = cache_module.load("dukascopy", "EURUSD", "H1")
    assert len(df) == 1
    assert df.iloc[0]["close"] == 1.105


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
    # Out-of-order, so this takes the full merge path -- the one that
    # swaps the file and therefore the one this property is about.
    cache_module.append("dukascopy", "EURUSD", "H1", [row("2023-06-01T00:00:00Z", 1.105, 1.115, 1.10, 1.11)])

    assert len(seen_readable_before_swap) == 1
    assert seen_readable_before_swap[0] != {}  # old file was still fully readable, not pre-truncated


def test_a_lock_file_owned_by_another_user_falls_back_rather_than_going_unlocked(monkeypatch):
    # Confirmed live: a diagnostic run as root left root-owned .lock files
    # beside abc-owned data, and the bot could no longer lock its own
    # cache. Silently dropping the lock removes the mutual exclusion
    # between the two live bot processes -- the exact race that crashed
    # one with EmptyDataError -- so an unopenable sidecar must fall back
    # to a usable location, not to no lock.
    cache_module.append("dukascopy", "EURUSD", "H1", [row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105)])
    path = cache_module.cache_path("dukascopy", "EURUSD", "H1")

    real_open = os.open

    def deny_sidecar(p, *a, **k):
        if str(p).endswith(f"{os.path.basename(path)}.lock"):
            raise PermissionError(13, "Permission denied")
        return real_open(p, *a, **k)

    monkeypatch.setattr(os, "open", deny_sidecar)
    added = cache_module.append("dukascopy", "EURUSD", "H1",
                                 [row("2024-01-01T01:00:00Z", 1.105, 1.115, 1.10, 1.11)])
    assert added == 1
    assert os.path.exists(cache_module._fallback_lock_path(path))
    assert len(cache_module.load("dukascopy", "EURUSD", "H1")) == 2


def test_the_lock_file_is_left_usable_by_other_users():
    cache_module.append("dukascopy", "EURUSD", "H1", [row("2024-01-01T00:00:00Z", 1.10, 1.11, 1.09, 1.105)])
    lock = cache_module.cache_path("dukascopy", "EURUSD", "H1") + ".lock"
    assert os.path.exists(lock)
    # Whichever user creates it first must not lock everyone else out.
    assert oct(os.stat(lock).st_mode)[-3:] == "666"
