"""
CLI: pull/update local OHLCV cache from Oanda for one instrument or all of
them, across every granularity STRATEGY.md's cascade needs.

Usage:
    python -m backtest.data_pipeline.fetch_oanda --all
    python -m backtest.data_pipeline.fetch_oanda --instrument EURUSD --granularity D
    python -m backtest.data_pipeline.fetch_oanda --instrument XAUUSD

Incremental by default: each symbol/granularity pair only fetches candles
newer than what's already cached, so re-running this daily is cheap.
"""

import argparse
import sys

from . import cache, oanda_client
from .instruments import OANDA_INSTRUMENTS, DEFAULT_GRANULARITIES


def fetch_one(internal_symbol: str, oanda_symbol: str, granularity: str) -> int:
    since = cache.last_cached_time("oanda", internal_symbol, granularity)
    rows = oanda_client.fetch_candles(oanda_symbol, granularity, since=since)
    added = cache.append("oanda", internal_symbol, granularity, rows)
    return added


def main():
    parser = argparse.ArgumentParser(description="Fetch/update Oanda OHLCV cache.")
    parser.add_argument("--instrument", help="Internal symbol, e.g. EURUSD (see instruments.py). Omit with --all to fetch everything.")
    parser.add_argument("--granularity", help="Single Oanda granularity code (e.g. D, H4, M15). Omits fetches DEFAULT_GRANULARITIES.")
    parser.add_argument("--all", action="store_true", help="Fetch every instrument in instruments.py.")
    args = parser.parse_args()

    if args.all:
        targets = list(OANDA_INSTRUMENTS.items())
    elif args.instrument:
        if args.instrument not in OANDA_INSTRUMENTS:
            sys.exit(f"Unknown instrument {args.instrument!r}. See instruments.py for the supported list.")
        targets = [(args.instrument, OANDA_INSTRUMENTS[args.instrument])]
    else:
        sys.exit("Pass --instrument SYMBOL or --all.")

    granularities = [args.granularity] if args.granularity else DEFAULT_GRANULARITIES

    for internal_symbol, oanda_symbol in targets:
        for granularity in granularities:
            added = fetch_one(internal_symbol, oanda_symbol, granularity)
            print(f"{internal_symbol:8s} {granularity:4s} +{added} candles")


if __name__ == "__main__":
    main()
