"""
Shared candle representation for the engine.

Deliberately a plain dataclass, not a pandas row -- structure.py's
StructureTracker and liquidity.py's helpers process candles one at a time
in a forward loop so the exact same code path can later replay live,
just-closed MT5 bars one by one instead of an in-memory backtest array.
"""

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


def load_candles(source: str, symbol: str, granularity: str) -> list[Candle]:
    """Load a cached OHLCV series (see data_pipeline/cache.py) as a time-ordered list of Candle."""
    df = cache.load(source, symbol, granularity)
    return [
        Candle(row.time, row.open, row.high, row.low, row.close, row.volume)
        for row in df.itertuples(index=False)
    ]
