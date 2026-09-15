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


# Fixed-interval granularities can only legitimately OPEN at specific UTC
# boundaries -- H4 at 00/04/08/12/16/20, D at midnight, W at Monday
# midnight (matching bot/mt5_data.py's _last_completed_open(), which
# assumes the same). Confirmed live 2026-09-15: every one of 25+
# instruments' D/W/H4 cache files carries a consistent ~150-200 rows that
# do NOT land on a valid boundary (e.g. H4 bars at 05:00/07:00/09:00
# instead of 04:00/08:00/12:00) -- same count regardless of instrument or
# total history length, which points at a shared historical stretch where
# dukascopy-python's own upstream resampling (not this pipeline -- H4/D/W
# are fetched as Dukascopy-native granularities, see dukascopy_client.py)
# produced off-boundary bars, likely a DST-adjacent quirk. Live structure/
# bias detection assumes every bar sits where it claims to
# (StructureTracker, live_strategy.py's storyline gate); feeding it one
# that doesn't produces visibly unstable output -- confirmed live: JP225's
# H4 bias flipped bullish/bearish twice within 30 seconds on the SAME
# already-running process, with no real H4 candle having closed in
# between. H1 has no such concept (any hour is a valid H1 open), so it is
# deliberately not in this set.
_VALID_BOUNDARY_HOURS = {"H4": {0, 4, 8, 12, 16, 20}, "D": {0}, "W": {0}}


def _is_valid_boundary(time: pd.Timestamp, granularity: str) -> bool:
    if granularity not in _VALID_BOUNDARY_HOURS:
        return True
    if time.minute != 0 or time.second != 0:
        return False
    if granularity == "W" and time.weekday() != 0:  # Monday
        return False
    return time.hour in _VALID_BOUNDARY_HOURS[granularity]


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
        if _is_valid_boundary(row.time, granularity)
    ]
    if fingerprint is not None:
        _cache[path] = (fingerprint, candles)
    return list(candles)
