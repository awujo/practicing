"""
Local OHLCV cache shared by both fetchers.

Layout: backtest/data/{source}/{symbol}/{granularity}.csv
Columns: time (ISO-8601 UTC), open, high, low, close, volume

Fetches are incremental: each fetcher asks `last_cached_time()` for a
symbol/granularity and only requests candles after that point, then
`append()` merges and dedupes rather than re-downloading history that's
already on disk.
"""

import os
import pandas as pd

DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def cache_path(source: str, symbol: str, granularity: str) -> str:
    return os.path.join(DATA_ROOT, source, symbol, f"{granularity}.csv")


def last_cached_time(source: str, symbol: str, granularity: str):
    """Return the UTC timestamp (str) of the most recent cached candle, or None if no cache yet."""
    path = cache_path(source, symbol, granularity)
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, usecols=["time"])
    if df.empty:
        return None
    return df["time"].max()


def append(source: str, symbol: str, granularity: str, rows: list[dict]):
    """Merge new candle rows into the cache, dedupe by time, keep sorted ascending."""
    if not rows:
        return 0
    path = cache_path(source, symbol, granularity)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    new_df = pd.DataFrame(rows, columns=COLUMNS)
    if os.path.exists(path):
        existing = pd.read_csv(path)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined = combined.drop_duplicates(subset="time").sort_values("time")
    combined.to_csv(path, index=False)
    return len(new_df)


def load(source: str, symbol: str, granularity: str) -> pd.DataFrame:
    path = cache_path(source, symbol, granularity)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No cached data for {source}/{symbol}/{granularity} -- run the fetcher first."
        )
    df = pd.read_csv(path, parse_dates=["time"])
    return df.sort_values("time").reset_index(drop=True)
