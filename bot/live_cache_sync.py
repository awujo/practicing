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
     CLOSED candles per granularity from MT5 onto that SAME cache series
     (same `source` name, not a separate namespace) every time it's
     called; cache.append() dedupes by timestamp, so repeated calls (one
     per new-candle-close event) only ever add genuinely new bars.

Acknowledged tradeoff: the historical portion of the resulting series
comes from Dukascopy, the live tail from the broker's own MT5 feed --
two different liquidity providers with (usually small, occasionally not)
different prices/spreads. This is the practical cost of not needing years
of tick history already downloaded inside the MT5 terminal itself.
"""

from backtest.data_pipeline import cache as cache_module
from backtest.webapp import data_access

from .mt5_data import MT5Client, GRANULARITIES


def bootstrap_historical_cache(instrument: str, source: str = "dukascopy") -> str:
    return data_access.ensure_instrument_cache(instrument, source=source)


def sync_recent_from_mt5(mt5_client: MT5Client, instrument: str, source: str = "dukascopy",
                          granularities: tuple[str, ...] = GRANULARITIES,
                          lookback_count: int = 10) -> dict[str, int]:
    appended = {}
    for granularity in granularities:
        candles = mt5_client.fetch_candles(instrument, granularity, count=lookback_count)
        rows = [
            {"time": c.time.isoformat(), "open": c.open, "high": c.high,
             "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        appended[granularity] = cache_module.append(source, instrument, granularity, rows)
    return appended
