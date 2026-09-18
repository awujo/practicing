"""
Keeps the on-disk candle cache (backtest/data_pipeline/cache.py) fresh
from MT5, so run_backtest() -- completely unmodified -- can be called
live and see current price action, rather than reimplementing its
entry-detection logic in a separate "streaming" form. That logic is
built around walking a full historical array (bias replay, structural
sweep/break detection, `claimed_origins` position-stacking state) --
genuinely not something to safely re-derive incrementally without
risking behavioral drift from the already-validated backtest path. This
module's only job is making sure the cache run_backtest reads from is
current; the orchestrator calls run_backtest(source=..., ...) itself and
looks at whether a fresh trade landed at the latest candle.

Two pieces, deliberately separate:

  1. `bootstrap_historical_cache()` -- pulls years of Dukascopy history
     via the SAME release-asset mechanism backtest/webapp/data_access.py
     already uses for the Render viewer (ensure_instrument_cache), once
     per instrument at startup. Gives structure/bias/key-level detection
     the deep lead-in it needs to "warm up" the same way it does in a
     real backtest -- starting the live cache cold with only MT5's
     recent bars would produce different, likely worse, signals than the
     backtest this strategy was actually validated against.

  2. `sync_recent_from_mt5()` -- appends the most recent handful of
     CLOSED H1 candles from MT5 onto that SAME cache series (same
     `source` name, not a separate namespace) every time it's called;
     cache.append() dedupes by timestamp, so repeated calls (one per new
     candle close) only ever add genuinely new bars. It then re-derives
     the H4/D/W tail from that H1. H4/D/W are never fetched from MT5 --
     see SYNC_GRANULARITIES for what went wrong when they were.

Acknowledged tradeoff: the historical portion of the resulting series
comes from Dukascopy, the live tail from the broker's own MT5 feed --
two different liquidity providers with (usually small, occasionally not)
different prices/spreads. This is the practical cost of not needing years
of tick history already downloaded inside the MT5 terminal itself.
"""

import pandas as pd

from backtest.data_pipeline import cache as cache_module
from backtest.data_pipeline.resample import REPAIRABLE_GRANULARITIES, resample_ohlcv
from backtest.webapp import data_access

from .mt5_data import MT5Client

# Only H1 is taken from MT5. H4/D/W are DERIVED from it (see
# `_derive_tail()`), never fetched from the broker.
#
# Why (2026-09-16, after a live investigation): this module used to sync
# all of ("D", "H4", "H1", "W") straight from MT5 onto the Dukascopy
# series. MT5 anchors bars to BROKER midnight -- the server runs UTC+3,
# so H4 lands on 01/05/09/13/17/21 UTC, daily on 21:00, weekly on
# Saturday 21:00. Dukascopy anchors to UTC midnight. Those are two
# different series, and appending one onto the other produces bars
# covering overlapping spans of time.
#
# `cache.append()` dedupes by TIMESTAMP, so it could never catch it: a
# 16:00 bar and a 17:00 bar are two different timestamps, both entirely
# plausible. The damage ran undetected from 2026-08-19 until it was
# found on 2026-09-16 -- by then GBPUSD H4 held bars on all 24 hours
# where a grid allows 6, with 173 rows sitting closer than one bar to
# the row before them and zero exact duplicates.
#
# H1 does not have this problem. An H1 bar is an H1 bar on either feed,
# because the broker offset is a whole number of hours -- verified by
# lag-matching cached H1 closes against the live terminal across ~700
# bars, where lag 0 beat every other offset by 40x on GBPUSD and 60x on
# XAUUSD. Deriving the rest from H1 means one anchor governs the whole
# series by construction, which is a property rather than a check.
SYNC_GRANULARITIES = ("H1",)

# How far back to re-derive after each sync. Must comfortably exceed the
# longest derived bar so the bin holding the newest H1 rows is rebuilt
# from ALL of its members, not just the ones that arrived this round --
# a weekly bar needs its whole week present or its OHLC is computed off
# a partial week.
DERIVE_LOOKBACK = pd.Timedelta(days=21)

# How long each derived bar spans, used to drop the trailing INCOMPLETE
# one. A 4H bin whose period has not finished yet is built from one, two
# or three closed H1 candles instead of four, and its high/low/close
# change every hour as the rest arrive -- so the same bar means something
# different on each sync, and bias computed from it flips underneath the
# strategy. The MT5 path this replaced avoided that by fetching with
# start=1, which skips the still-forming bar; deriving has to do the
# equivalent explicitly. See mt5_data.fetch_candles: "a strategy decision
# must never be made against an incomplete candle -- structure.py's
# swing/sweep logic assumes every candle it sees is finished."
DERIVED_PERIODS = {
    "H4": pd.Timedelta(hours=4),
    "D": pd.Timedelta(days=1),
    "W": pd.Timedelta(days=7),
}


def bootstrap_historical_cache(instrument: str, source: str = "dukascopy") -> str:
    return data_access.ensure_instrument_cache(instrument, source=source)


def _derive_tail(instrument: str, source: str, lookback: pd.Timedelta) -> dict[str, int]:
    """Rebuild the recent H4/D/W tail from cached H1.

    Rewrites rather than appends: a derived bar that was computed from a
    partial H1 bin last round must be REPLACED once the rest of its
    hours arrive, and appending would leave the stale version sitting
    there under the same timestamp."""
    written = {}
    h1 = cache_module.load(source, instrument, "H1")
    h1 = h1.copy()
    h1["time"] = pd.to_datetime(h1["time"], utc=True)
    if h1.empty:
        return written

    cut = h1["time"].max() - lookback
    window = h1[h1["time"] >= cut]
    # The newest H1 row covers [last_h1, last_h1 + 1h), so a derived bin
    # is finished only once its whole period falls inside that.
    last_h1 = window["time"].max()
    for granularity, (_src, rule, kwargs) in REPAIRABLE_GRANULARITIES.items():
        out = resample_ohlcv(window, rule, **kwargs)
        # Drop the first derived bar: its bin starts before `cut`, so it
        # is aggregated from a partial set of H1 rows and would overwrite
        # a correct bar with a truncated one.
        out = out.iloc[1:]
        # Drop any trailing bar whose period has not completed. Without
        # this, every sync rewrites the in-progress bar with different
        # OHLC and the strategy sees its most recent candle change shape
        # under it.
        period = DERIVED_PERIODS[granularity]
        out = out[out["time"] + period <= last_h1 + pd.Timedelta(hours=1)]
        if out.empty:
            written[granularity] = 0
            continue

        # Nothing new completed -> don't rewrite the file.
        #
        # This sync runs hourly, but an H4 bar only completes every 4
        # hours, a daily every 24 and a weekly every 168. So most calls
        # would read 40,000 rows and write 40,000 identical rows back.
        # Measured on the live VPS 2026-09-18: 13-22 seconds per
        # instrument for the three granularities, against a loop that was
        # taking ~2 minutes per instrument and ~50 minutes per full cycle
        # -- while H1 candles close every 60. The bot was making itself
        # late.
        #
        # Comparing the newest derived bar against the newest bar on disk
        # is enough, because every bar written here is COMPLETE (see
        # DERIVED_PERIODS) and complete bars are built from closed H1
        # candles that do not change afterwards. newest_cached_time()
        # reads the file's tail rather than parsing it, so the check
        # itself is cheap.
        #
        # None from that call means "could not tell", which falls through
        # to writing -- correct, not clever.
        newest_on_disk = cache_module.newest_cached_time(source, instrument, granularity)
        newest_derived = out["time"].iloc[-1].isoformat().replace("+00:00", "Z")
        if newest_on_disk is not None and newest_derived <= newest_on_disk:
            written[granularity] = 0
            continue

        rows = [
            {"time": r["time"].isoformat().replace("+00:00", "Z"),
             "open": r["open"], "high": r["high"], "low": r["low"],
             "close": r["close"], "volume": r["volume"]}
            for _, r in out.iterrows()
        ]
        _dropped, n = cache_module.replace_from(
            source, instrument, granularity, rows[0]["time"], rows)
        written[granularity] = n
    return written


def sync_recent_from_mt5(mt5_client: MT5Client, instrument: str, source: str = "dukascopy",
                          granularities: tuple[str, ...] = SYNC_GRANULARITIES,
                          lookback_count: int = 10,
                          derive_lookback: pd.Timedelta = DERIVE_LOOKBACK) -> dict[str, int]:
    appended = {}
    for granularity in granularities:
        candles = mt5_client.fetch_candles(instrument, granularity, count=lookback_count)
        rows = [
            # Matches the exact format every other writer in the data
            # pipeline uses (dukascopy_client.py, fetch_crypto.py,
            # resample.py) -- "+00:00" replaced with "Z". Mixing this
            # with the plain isoformat() (which keeps "+00:00") in the
            # same CSV column is what caused a real crash: pandas
            # partially fails to parse a column with two different ISO
            # variants, leaving some rows as real Timestamps and others
            # as raw strings, which blows up any later comparison
            # between them (confirmed live -- TypeError: '>' not
            # supported between instances of 'Timestamp' and 'str').
            {"time": c.time.isoformat().replace("+00:00", "Z"), "open": c.open, "high": c.high,
             "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        appended[granularity] = cache_module.append(source, instrument, granularity, rows)

    if "H1" in granularities:
        appended.update(_derive_tail(instrument, source, derive_lookback))
    return appended
