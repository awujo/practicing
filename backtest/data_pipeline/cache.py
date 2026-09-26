"""
Local OHLCV cache shared by both fetchers.

Layout: backtest/data/{source}/{symbol}/{granularity}.csv
Columns: time (ISO-8601 UTC), open, high, low, close, volume

Fetches are incremental: each fetcher asks `last_cached_time()` for a
symbol/granularity and only requests candles after that point, then
`append()` merges and dedupes rather than re-downloading history that's
already on disk.

`append()` has a fast path that matters enormously for the live bot.
Measured on the live VPS, adding 10 candles to EURUSD's H1.csv via the
original full read-merge-rewrite took **36.4 seconds** -- 15.8s to
`pd.read_csv` 9.4MB / 155k rows, 2.3s to concat+dedupe+sort, 18.3s to
write it all back. Per granularity, per instrument, per sync, on two
bots sharing the same files: roughly 20 minutes of work per pass per
bot, which is what put the live bots hours behind and made them miss
real setups (see bot/OPERATIONS_LOG.md, 2026-08-26).

The overwhelmingly common live case is "these candles are all at or
before the newest one already cached, plus maybe one or two genuinely
new ones at the end". That needs no merge at all: read just the final
line to learn the newest cached timestamp, drop everything at or before
it, and append what's left. Nothing new at all -- the usual outcome --
costs one short seek and zero writes.
"""

import fcntl
import hashlib
import logging
import os
import tempfile
from contextlib import contextmanager

import pandas as pd

logger = logging.getLogger("backtest.data_pipeline.cache")

DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def cache_path(source: str, symbol: str, granularity: str) -> str:
    return os.path.join(DATA_ROOT, source, symbol, f"{granularity}.csv")


def _fallback_lock_path(path: str) -> str:
    """A lock location that doesn't depend on the data directory's
    ownership: a world-writable shared temp dir, keyed by a hash of the
    real path so two different caches can't collide.

    Used only when the sidecar next to the CSV can't be opened. Losing
    the lock entirely would drop the mutual exclusion between the two
    live bot processes -- the exact thing that crashed one with
    EmptyDataError -- so falling back to a different location is much
    better than falling back to no lock at all."""
    digest = hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), "slk-cache-locks", digest + ".lock")


@contextmanager
def _file_lock(path: str, exclusive: bool):
    """Coordinate readers and writers across processes.

    Two live bot processes (conservative + aggressive) read and write the
    SAME cache files concurrently, and a reader catching a writer
    mid-update is not hypothetical -- it crashed a live bot with
    `pandas.errors.EmptyDataError` on 2026-08-26. The lock is held on a
    sidecar `.lock` file rather than the CSV itself, because the
    full-merge path below swaps the CSV's inode via `os.replace()`, which
    a lock on the old inode would not survive.

    Readers take a shared lock (they don't block each other); writers take
    an exclusive one. The fast append path holds the write lock for
    microseconds; only the rare full merge holds it meaningfully long."""
    handle = None
    for lock_file in (path + ".lock", _fallback_lock_path(path)):
        try:
            os.makedirs(os.path.dirname(lock_file), exist_ok=True)
            # Mode 0o666 (umask permitting) plus an explicit chmod: which
            # user happens to create the lock first must not decide who
            # can use it afterwards. Confirmed live -- a diagnostic run as
            # root left root-owned .lock files next to abc-owned data, and
            # the bot then couldn't lock its own cache.
            fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o666)
            try:
                os.fchmod(fd, 0o666)
            except OSError:
                pass  # not ours to chmod; if we could open it, that's enough
            handle = os.fdopen(fd, "r+")
            break
        except OSError:
            continue

    if handle is None:
        # Both the sidecar and the shared fallback are unusable. Degrade
        # to the pre-locking behavior rather than raising into the
        # caller's loop -- still safe against a torn read, since append()
        # writes in one call and the merge path swaps atomically via
        # os.replace().
        logger.warning("cache lock unavailable for %s -- proceeding without it", path)
        yield
        return
    try:
        fcntl.flock(handle, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            handle.close()


TAIL_BYTES = 65536  # ~1,000 H1 rows: far more than any live sync submits


def _tail_index(path: str, nbytes: int = TAIL_BYTES):
    """`(last_time, times_in_tail)` read from the end of the file rather
    than by parsing all of it -- the point of the fast path.

    `times_in_tail` matters for correctness, not just speed: a submitted
    row OLDER than `last_time` might be a genuine gap-fill that isn't on
    disk, and appending only the newer rows would silently lose it. The
    caller checks membership here and falls back to the full merge when
    it can't prove the older rows are already present.

    Returns None for a missing, empty or header-only file, or anything
    not in the expected ISO-8601 'Z' format -- all of which mean "don't
    risk the fast path"."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size == 0:
        return None
    start = max(0, size - nbytes)
    with open(path, "rb") as f:
        f.seek(start)
        tail = f.read().decode("utf-8", errors="replace")
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    # A non-zero start almost certainly lands mid-line; that first
    # fragment isn't a whole row, so it can't be trusted for membership.
    if start > 0 and lines:
        lines = lines[1:]
    if not lines:
        return None
    times = {ln.split(",")[0].strip() for ln in lines}
    last = lines[-1].split(",")[0].strip()
    if not last.endswith("Z"):
        return None  # header-only file, or a format we can't order safely
    return last, times


def _append_rows(path: str, rows: list[dict]) -> None:
    """Append rows as CSV lines in a SINGLE write() call.

    One small write to a file opened O_APPEND is not split by the kernel,
    so a concurrent reader sees either none of it or all of it -- and
    readers hold a shared lock against this anyway (see _file_lock).
    Deliberately not pandas: building a DataFrame to emit a handful of
    lines is most of the cost this fast path exists to avoid."""
    payload = "".join(
        ",".join("" if row.get(col) is None else str(row.get(col)) for col in COLUMNS) + "\n"
        for row in rows
    )
    with open(path, "a", newline="") as f:
        f.write(payload)


def newest_cached_time(source: str, symbol: str, granularity: str):
    """The newest cached candle's time, read from the END of the file
    rather than by parsing all of it -- or None if that can't be done
    cheaply and safely.

    `last_cached_time()` does the same job with pd.read_csv over the
    whole time column. That is fine occasionally and far too expensive in
    a hot loop: on this cache a 40,000-row H4 file costs ~2.5s just to
    load, and the live sync asks per instrument, per granularity, every
    hour.

    None means "could not tell from the tail" (missing, empty, or not in
    the expected ISO-8601 'Z' format), which callers must treat as "do
    the full thing", never as "there is nothing there".
    """
    index = _tail_index(cache_path(source, symbol, granularity))
    return index[0] if index is not None else None


def last_cached_time(source: str, symbol: str, granularity: str):
    """Return the UTC timestamp (str) of the most recent cached candle, or None if no cache yet."""
    path = cache_path(source, symbol, granularity)
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, usecols=["time"])
    if df.empty:
        return None
    return df["time"].max()


def newest_candle_time(source: str, symbol: str, granularity: str):
    """The most recent cached candle's timestamp, read from the tail.

    `last_cached_time()` above reads the whole time column, which is a
    full pass over a 9MB file. This reads the last block only, which is
    what a poll loop needs: the question "has anything closed since I
    last looked" is asked every minute per instrument and must cost
    almost nothing, or the asking becomes the work.

    None when there is no cache or it cannot be read -- a caller should
    then do its normal thing rather than treat that as "no new data".
    """
    try:
        frame = load_tail(source, symbol, granularity, 1)
    except Exception:                                   # noqa: BLE001
        return None
    if frame.empty:
        return None
    return frame["time"].iloc[-1]


def append(source: str, symbol: str, granularity: str, rows: list[dict]):
    """Merge new candle rows into the cache, dedupe by time, keep sorted ascending.

    Takes the cheap append-only path when every row worth keeping sorts
    after everything already cached (see the module docstring); otherwise
    falls back to the full read-merge-rewrite below, which stays correct
    for out-of-order rows, backfills, and first writes."""
    if not rows:
        return 0
    path = cache_path(source, symbol, granularity)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with _file_lock(path, exclusive=True):
        index = _tail_index(path) if os.path.exists(path) else None
        if index is not None:
            last_cached, tail_times = index
            times = [str(row.get("time")) for row in rows]
            if all(t.endswith("Z") for t in times):
                fresh = [r for r, t in zip(rows, times) if t > last_cached]
                older = [t for t in times if t <= last_cached]
                # Every row we're NOT appending must already be on disk,
                # or it's a gap-fill that appending would silently lose.
                # Anything older than the tail window can't be proven
                # present from here, so it merges -- correct, just slower.
                if all(t in tail_times for t in older):
                    if not fresh:
                        return 0  # nothing new -- the usual live case, and free
                    fresh_times = [str(r["time"]) for r in fresh]
                    # Strictly increasing among themselves and all newer
                    # than disk, so appending preserves sort + uniqueness.
                    if (len(set(fresh_times)) == len(fresh_times)
                            and fresh_times == sorted(fresh_times)):
                        _append_rows(path, fresh)
                        return len(fresh)
        return _merge_rewrite(path, rows)


def _merge_rewrite(path: str, rows: list[dict]) -> int:
    """The original full read-merge-rewrite. Correct for any input, but
    reads and rewrites the entire file -- only for cases the append-only
    fast path in `append()` can't safely handle. Caller holds the lock."""
    new_df = pd.DataFrame(rows, columns=COLUMNS)
    if os.path.exists(path):
        existing = pd.read_csv(path)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined = combined.drop_duplicates(subset="time").sort_values("time")

    # Write atomically -- confirmed live: two bot processes (conservative +
    # aggressive) both call append() for the SAME instrument/granularity
    # file concurrently. A plain to_csv(path) truncates then writes in
    # place, so a concurrent reader in the OTHER process can catch the
    # file mid-truncation and see it as empty -- crashed a live bot with
    # pandas.errors.EmptyDataError. Writing to a temp file in the same
    # directory and os.replace()-ing it into place is atomic on POSIX, so
    # a concurrent reader always sees either the complete old file or the
    # complete new one, never a partial state.
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    os.close(tmp_fd)
    try:
        combined.to_csv(tmp_path, index=False)
        os.replace(tmp_path, path)
    except BaseException:
        os.remove(tmp_path)
        raise
    return len(new_df)


def replace_from(source: str, symbol: str, granularity: str, cutoff: str,
                  rows: list[dict]) -> tuple[int, int]:
    """Drop every cached row at or after `cutoff` and put `rows` in their
    place. Returns (rows_dropped, rows_written).

    `append()` cannot do this. It MERGES, deduping by timestamp -- which
    is exactly why the 2026-08 damage accumulated silently: bars from a
    differently-anchored feed carry timestamps that no dedupe can
    recognise as wrong, because a 16:00 bar and a 17:00 bar really are
    two different timestamps. Removing them needs a delete, and a delete
    needs its own function rather than a flag on the merge path.

    `cutoff` is an ISO-8601 UTC string in the same format the cache
    stores ("...Z"), compared as a string exactly as `append()` compares
    timestamps -- consistent ordering with the rest of this module, and
    no timezone parsing to get subtly wrong on a destructive operation.

    Writes atomically via a temp file plus os.replace(), for the same
    reason `_merge_rewrite()` does: two bot processes read these files
    concurrently and a plain truncate-then-write lets one of them see an
    empty file (a real crash, see that function's note)."""
    path = cache_path(source, symbol, granularity)
    with _file_lock(path, exclusive=True):
        if os.path.exists(path):
            existing = pd.read_csv(path)
            keep = existing[existing["time"].astype(str) < cutoff]
            dropped = len(existing) - len(keep)
        else:
            keep = pd.DataFrame(columns=COLUMNS)
            dropped = 0

        new_df = pd.DataFrame(rows, columns=COLUMNS)
        combined = pd.concat([keep, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset="time").sort_values("time")

        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        os.close(tmp_fd)
        try:
            combined.to_csv(tmp_path, index=False)
            os.replace(tmp_path, path)
        except BaseException:
            os.remove(tmp_path)
            raise
    return dropped, len(new_df)


def load_tail(source: str, symbol: str, granularity: str,
              rows: int) -> pd.DataFrame:
    """The last `rows` candles, read WITHOUT parsing the whole file.

    `load()` reads every row and the caller then throws most of them
    away. That is right for a backtest, which wants all of it, and badly
    wrong for the live side, which wants one or two years: EURUSD's H1 is
    9.4MB and 155k rows, and pandas takes about sixteen seconds over it.
    Four series per instrument, 27 instruments, once an hour -- measured
    on the VPS at SEVENTY SECONDS PER INSTRUMENT, or half an hour a
    cycle, essentially all of it spent parsing rows that were then
    discarded.

    So this seeks from the END and parses only what it needs. The file is
    append-only and time-ordered, which is what makes that safe.

    Falls back to a full `load()` when the file is smaller than the tail
    it would read, or when the tail turns out to hold fewer rows than
    asked for -- correctness first, speed second, and never a silently
    short series.
    """
    path = cache_path(source, symbol, granularity)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No cached data for {source}/{symbol}/{granularity} -- run the fetcher first."
        )
    if rows <= 0:
        return load(source, symbol, granularity)

    with _file_lock(path, exclusive=False):
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            header = handle.readline()
            # Read backwards in doubling chunks until there are enough
            # newlines, or the whole file has been read.
            want = rows + 1                       # +1: the first line is partial
            chunk = max(1 << 16, rows * 64)
            data = b""
            while True:
                start = max(len(header), size - chunk)
                handle.seek(start)
                data = handle.read(size - start)
                if data.count(b"\n") >= want or start <= len(header):
                    break
                chunk *= 2
            complete_from_start = start <= len(header)

    lines = data.split(b"\n")
    if not complete_from_start:
        lines = lines[1:]                          # drop the partial first line
    lines = [ln for ln in lines if ln.strip()][-rows:]
    if not lines:
        return load(source, symbol, granularity)

    import io
    frame = pd.read_csv(io.BytesIO(header + b"\n".join(lines)),
                         parse_dates=["time"])
    return frame.sort_values("time").reset_index(drop=True)


def load(source: str, symbol: str, granularity: str) -> pd.DataFrame:
    path = cache_path(source, symbol, granularity)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No cached data for {source}/{symbol}/{granularity} -- run the fetcher first."
        )
    # Shared lock: every read of the cache goes through here (candles.py's
    # load_candles(), and therefore run_backtest()), so taking it here is
    # what makes the writer's lock in append() actually mean something.
    with _file_lock(path, exclusive=False):
        df = pd.read_csv(path, parse_dates=["time"])
    return df.sort_values("time").reset_index(drop=True)
