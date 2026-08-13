"""
CLI: pull/update local OHLCV cache from Dukascopy -- the primary data
source (see instruments.py's module docstring for why: no account, no
KYC, works from any normal internet connection).

Usage:
    python -m backtest.data_pipeline.fetch_dukascopy --all
    python -m backtest.data_pipeline.fetch_dukascopy --instrument EURUSD --granularity D
    python -m backtest.data_pipeline.fetch_dukascopy --instrument XAUUSD

Must be run somewhere with normal outbound internet access -- it cannot
run inside this Claude Code cloud session, which blocks all external
market-data hosts at the network policy level (confirmed by testing
Dukascopy, Oanda, Twelve Data, and Binance -- all identically rejected).
Run this on your own machine after `pip install -r requirements.txt`.

Incremental by default: each symbol/granularity pair only fetches candles
newer than what's already cached, so re-running this daily is cheap.
"""

import argparse
import sys

from . import cache
from .dukascopy_client import fetch_candles
from .instruments import DUKASCOPY_INSTRUMENTS, DEFAULT_GRANULARITIES


def fetch_one(internal_symbol: str, granularity: str) -> int:
    since = cache.last_cached_time("dukascopy", internal_symbol, granularity)
    rows = fetch_candles(internal_symbol, granularity, since=since)
    added = cache.append("dukascopy", internal_symbol, granularity, rows)
    return added


def main():
    parser = argparse.ArgumentParser(description="Fetch/update Dukascopy OHLCV cache.")
    parser.add_argument("--instrument", help="Internal symbol, e.g. EURUSD (see instruments.py). Omit with --all to fetch everything.")
    parser.add_argument("--granularity", help="Single granularity code (e.g. D, H4, M15). Omit to fetch DEFAULT_GRANULARITIES.")
    parser.add_argument("--all", action="store_true", help="Fetch every instrument in instruments.py.")
    args = parser.parse_args()

    if args.all:
        targets = list(DUKASCOPY_INSTRUMENTS.keys())
    elif args.instrument:
        if args.instrument not in DUKASCOPY_INSTRUMENTS:
            sys.exit(f"Unknown instrument {args.instrument!r}. See instruments.py for the supported list.")
        targets = [args.instrument]
    else:
        sys.exit("Pass --instrument SYMBOL or --all.")

    granularities = [args.granularity] if args.granularity else DEFAULT_GRANULARITIES

    for internal_symbol in targets:
        for granularity in granularities:
            added = fetch_one(internal_symbol, granularity)
            print(f"{internal_symbol:8s} {granularity:4s} +{added} candles")


if __name__ == "__main__":
    main()
