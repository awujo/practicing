"""
CLI: derive H2/H3/M45 from already-cached H1/M15 data (see resample.py
for why these aren't fetched directly -- Dukascopy has no native H2, H3,
or M45 granularity).

Run this AFTER fetch_dukascopy.py has populated H1 (for H2/H3) and/or
M15 (for M45) for the instrument(s) you need. Purely local -- no network
call, so it's fast and works offline.

Usage:
    python -m backtest.data_pipeline.derive_granularities --all
    python -m backtest.data_pipeline.derive_granularities --instrument EURUSD
    python -m backtest.data_pipeline.derive_granularities --instrument EURUSD --granularity H2
"""

import argparse
import sys

from .instruments import DUKASCOPY_INSTRUMENTS
from .resample import DERIVED_GRANULARITIES, derive


def main():
    parser = argparse.ArgumentParser(description="Derive H2/H3/M45 from cached H1/M15 data.")
    parser.add_argument("--instrument", help="Internal symbol, e.g. EURUSD. Omit with --all to derive for everything.")
    parser.add_argument("--granularity", choices=sorted(DERIVED_GRANULARITIES), help="Omit to derive H2, H3, and M45 all at once.")
    parser.add_argument("--all", action="store_true", help="Derive for every instrument in instruments.py.")
    args = parser.parse_args()

    if args.all:
        targets = list(DUKASCOPY_INSTRUMENTS.keys())
    elif args.instrument:
        if args.instrument not in DUKASCOPY_INSTRUMENTS:
            sys.exit(f"Unknown instrument {args.instrument!r}. See instruments.py for the supported list.")
        targets = [args.instrument]
    else:
        sys.exit("Pass --instrument SYMBOL or --all.")

    granularities = [args.granularity] if args.granularity else sorted(DERIVED_GRANULARITIES)

    for symbol in targets:
        for granularity in granularities:
            try:
                added = derive("dukascopy", symbol, granularity)
                print(f"{symbol:8s} {granularity:4s} +{added} candles")
            except FileNotFoundError as e:
                print(f"{symbol:8s} {granularity:4s} skipped -- {e}")


if __name__ == "__main__":
    main()
