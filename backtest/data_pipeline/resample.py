"""
Derives Dukascopy-unsupported granularities (H2, H3, M45) from cached
native ones (H1 -> H2/H3, M15 -> M45) via local OHLCV resampling. No
network call -- runs entirely against what's already in the cache, so
it's fast and has nothing to do with Dukascopy reachability.

Anchoring assumption worth being explicit about: bins are anchored to
UTC midnight (pandas `origin="start_day"`), i.e. H2 = 00:00-02:00,
02:00-04:00, ... and M45 = 00:00-00:45, 00:45-01:30, ... (1440 minutes /
45 = 32 -- divides evenly, so this tiles cleanly with no leftover
partial bin). STRATEGY.md doesn't specify what anchor MT5/TradingView use
for these non-standard intervals, so this is a stated assumption, not a
confirmed match -- same spirit as the data-feed caveat already in
STRATEGY.md Section 2 (candle closes can differ slightly between
brokers/feeds). If your MT5 broker's actual H2/H3/M45 bars turn out to
be anchored differently, that's the first thing to check if backtest
results on those timeframes look off from what you see live.
"""

import pandas as pd

from . import cache

# derived granularity -> (source granularity to resample from, pandas resample rule)
DERIVED_GRANULARITIES = {
    "H2": ("H1", "2h"),
    "H3": ("H1", "3h"),
    "M45": ("M15", "45min"),
}

# H4/D/W are FETCHED natively from Dukascopy, so they are not in
# DERIVED_GRANULARITIES above -- deriving them by default would silently
# replace a fetched series with a computed one. They are derivable here
# for one specific job: repairing a cache whose H4/D/W tail was polluted
# by bars from a different feed on a different anchor.
#
# What went wrong (2026-08, found 2026-09-16): live_cache_sync.py
# appended MT5's H4/D/W bars onto the Dukascopy series. MT5 anchors its
# bars to BROKER midnight (UTC+3, so 01/05/09/13/17/21 UTC); Dukascopy
# anchors to UTC midnight (00/04/08/12/16/20). Those are different
# series, and interleaving them produces overlapping bars covering
# overlapping spans of time. cache.append() dedupes by TIMESTAMP, so it
# could never catch it: a 16:00 bar and a 17:00 bar are two different
# timestamps, both plausible. Result on GBPUSD H4: 24 distinct hours
# where a grid allows 6, and 173 rows sitting closer than one bar to the
# row before them. Daily went from 26 rows a month to 162.
#
# Deriving from H1 instead removes the bug class rather than patching
# it: H1 splices cleanly across feeds (the broker offset is whole hours,
# so an H1 bar is an H1 bar either way), and one anchor then governs the
# whole series by construction.
REPAIRABLE_GRANULARITIES = {
    # granularity -> (source, rule, resample kwargs)
    "H4": ("H1", "4h", {"origin": "start_day"}),
    "D": ("H1", "1D", {"origin": "start_day"}),
    # Dukascopy's weekly bars are stamped on Mondays at 00:00 (verified:
    # GBPUSD W runs from 2003-04-28, a Monday, every row at hour 0), so
    # the bins must run Monday-to-Monday and carry the OPENING Monday's
    # label. "origin" is not accepted alongside a weekly anchor rule.
    "W": ("H1", "W-MON", {}),
}


def resample_ohlcv(df: pd.DataFrame, rule: str, **resample_kwargs) -> pd.DataFrame:
    """
    df: DataFrame with a "time" column (parsed timestamps) plus
    open/high/low/close/volume, as returned by cache.load(). Returns the
    same shape, resampled to `rule`. Empty bins (weekends, feed gaps) are
    dropped rather than emitted as synthetic flat candles.

    `resample_kwargs` overrides the binning arguments -- needed because
    pandas rejects `origin` alongside an anchored weekly rule like
    "W-MON". `label`/`closed` stay "left" regardless: a candle is stamped
    with the time it OPENED, which is the convention every other series
    in the cache uses and what the whole engine assumes.
    """
    kwargs = {"origin": "start_day"}
    kwargs.update(resample_kwargs)
    indexed = df.set_index("time")
    out = indexed.resample(rule, label="left", closed="left", **kwargs).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })
    out = out.dropna(subset=["open"])
    return out.reset_index()


def derive(source: str, symbol: str, derived_granularity: str) -> int:
    """Resample the cached source-granularity data and append the result
    into the derived granularity's own cache file. Returns rows added."""
    if derived_granularity not in DERIVED_GRANULARITIES:
        raise KeyError(
            f"{derived_granularity!r} is not derivable -- see DERIVED_GRANULARITIES "
            f"for the supported set (H2, H3, M45)"
        )
    from_granularity, rule = DERIVED_GRANULARITIES[derived_granularity]
    src_df = cache.load(source, symbol, from_granularity)  # raises if source not fetched yet
    out_df = resample_ohlcv(src_df, rule)

    rows = out_df.to_dict("records")
    for row in rows:
        row["time"] = row["time"].isoformat().replace("+00:00", "Z")

    return cache.append(source, symbol, derived_granularity, rows)
