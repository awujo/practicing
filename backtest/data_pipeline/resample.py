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


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """
    df: DataFrame with a "time" column (parsed timestamps) plus
    open/high/low/close/volume, as returned by cache.load(). Returns the
    same shape, resampled to `rule`. Empty bins (weekends, feed gaps) are
    dropped rather than emitted as synthetic flat candles.
    """
    indexed = df.set_index("time")
    out = indexed.resample(rule, origin="start_day", label="left", closed="left").agg({
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
