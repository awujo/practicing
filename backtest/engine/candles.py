"""
Shared candle representation for the engine.

Deliberately a plain dataclass, not a pandas row -- structure.py's
StructureTracker and liquidity.py's helpers process candles one at a time
in a forward loop so the exact same code path can later replay live,
just-closed MT5 bars one by one instead of an in-memory backtest array.
"""

import os
from dataclasses import dataclass
import pandas as pd

from ..data_pipeline import cache


@dataclass(frozen=True)
class Candle:
    time: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


# In-process cache of the parsed candle list per cache FILE PATH (not per
# source/symbol/granularity -- tests monkeypatch DATA_ROOT per test, so the
# same "dukascopy"/"EURUSD"/"H1" tuple can resolve to a different file
# across tests, and keying by the tuple alone would leak one test's data
# into another's). Value is (fingerprint, candles); fingerprint is the
# file's (size, mtime) at read time, cheap to re-check with a single
# os.stat() and exact enough to tell "unchanged since last read" from
# "actually got new rows appended."
#
# Why this exists (2026-09-11, from a live profile): a single
# run_backtest() call was costing 54-73s on the production VPS, and 34.5s
# of that -- 29% -- was this file being re-read off disk and re-parsed
# into fresh Candle objects EVERY time, including when NOTHING about it
# had changed since the previous call seconds earlier. The underlying
# cache file only changes once an hour, when sync_recent_from_mt5()
# appends a handful of rows -- there is no reason every one of the many
# calls in between should pay pandas.read_csv() plus a half-million-plus
# object-construction listcomp again. This does not shrink the SIZE of
# what gets parsed (the algorithmic cost of replaying years of history is
# a separate, larger problem, deliberately not touched here -- see
# OPERATIONS_LOG.md) -- it only stops parsing it repeatedly when nothing
# new has arrived.
_cache: dict[str, tuple[tuple[int, float], list["Candle"]]] = {}


def load_candles(source: str, symbol: str, granularity: str) -> list[Candle]:
    """Load a cached OHLCV series (see data_pipeline/cache.py) as a time-ordered list of Candle.

    Returns a fresh list object on every call (a shallow copy when served
    from cache) so a caller mutating the list it got back -- sorting it,
    appending to it -- can never corrupt what the next caller sees. The
    Candle objects themselves are frozen and shared either way, which is
    safe since nothing may mutate them.
    """
    path = cache.cache_path(source, symbol, granularity)
    try:
        stat = os.stat(path)
        fingerprint = (stat.st_size, stat.st_mtime)
    except OSError:
        fingerprint = None  # missing/unreadable -- fall through to cache.load()'s own error

    cached = _cache.get(path)
    if fingerprint is not None and cached is not None and cached[0] == fingerprint:
        return list(cached[1])

    df = cache.load(source, symbol, granularity)
    candles = [
        Candle(row.time, row.open, row.high, row.low, row.close, row.volume)
        for row in df.itertuples(index=False)
    ]
    if fingerprint is not None:
        _cache[path] = (fingerprint, candles)
    return list(candles)
