"""
CLI: pull/update local OHLCV cache for crypto instruments via ccxt.

Crypto isn't on Oanda, so this is a separate, structurally similar
fetcher writing into the same cache format (backtest/data/ccxt/{symbol}/{granularity}.csv)
so downstream backtest code doesn't need to care which source a symbol
came from.

Usage:
    python -m backtest.data_pipeline.fetch_crypto --all
    python -m backtest.data_pipeline.fetch_crypto --instrument ETHUSDT --granularity D
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import ccxt

from . import cache
from .instruments import CCXT_INSTRUMENTS, DEFAULT_GRANULARITIES

# ccxt timeframe strings differ from Oanda's granularity codes -- map ours
# to theirs. ccxt has no native monthly/weekly-from-H4 equivalents beyond
# what's listed; anything absent here isn't fetchable for crypto and is
# skipped with a warning.
GRANULARITY_TO_CCXT = {
    "M": "1M",
    "W": "1w",
    "D": "1d",
    "H4": "4h",
    "H1": "1h",
    "M30": "30m",
    "M15": "15m",
    "M5": "5m",
}

MAX_BARS_PER_REQUEST = 1000


def fetch_one(exchange_id: str, symbol: str, internal_symbol: str, granularity: str) -> int:
    ccxt_tf = GRANULARITY_TO_CCXT.get(granularity)
    if ccxt_tf is None:
        print(f"  skipping {granularity} -- no ccxt equivalent (see GRANULARITY_TO_CCXT)")
        return 0

    exchange = getattr(ccxt, exchange_id)()
    since_str = cache.last_cached_time("ccxt", internal_symbol, granularity)
    since_ms = (
        int(datetime.fromisoformat(since_str.replace("Z", "+00:00")).timestamp() * 1000)
        if since_str
        else exchange.parse8601("2017-01-01T00:00:00Z")
    )

    all_rows = []
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    cursor = since_ms
    while cursor < now_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=ccxt_tf, since=cursor, limit=MAX_BARS_PER_REQUEST)
        if not batch:
            break
        for ts, o, h, l, c, v in batch:
            all_rows.append({
                "time": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "open": o, "high": h, "low": l, "close": c, "volume": v,
            })
        cursor = batch[-1][0] + 1
        if len(batch) < MAX_BARS_PER_REQUEST:
            break
        time.sleep(exchange.rateLimit / 1000)

    # Drop the still-forming current bar (its close hasn't happened yet).
    if all_rows:
        all_rows = all_rows[:-1]

    return cache.append("ccxt", internal_symbol, granularity, all_rows)


def main():
    parser = argparse.ArgumentParser(description="Fetch/update crypto OHLCV cache via ccxt.")
    parser.add_argument("--instrument", help="Internal symbol, e.g. ETHUSDT (see instruments.py).")
    parser.add_argument("--granularity", help="Single granularity code (e.g. D, H4). Omit to fetch DEFAULT_GRANULARITIES.")
    parser.add_argument("--all", action="store_true", help="Fetch every crypto instrument in instruments.py.")
    args = parser.parse_args()

    if args.all:
        targets = list(CCXT_INSTRUMENTS.items())
    elif args.instrument:
        if args.instrument not in CCXT_INSTRUMENTS:
            sys.exit(f"Unknown instrument {args.instrument!r}. See instruments.py for the supported list.")
        targets = [(args.instrument, CCXT_INSTRUMENTS[args.instrument])]
    else:
        sys.exit("Pass --instrument SYMBOL or --all.")

    granularities = [args.granularity] if args.granularity else DEFAULT_GRANULARITIES

    for internal_symbol, cfg in targets:
        for granularity in granularities:
            added = fetch_one(cfg["exchange"], cfg["symbol"], internal_symbol, granularity)
            print(f"{internal_symbol:8s} {granularity:4s} +{added} candles")


if __name__ == "__main__":
    main()
