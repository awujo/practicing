"""
Print, in plain language, what the engine actually sees on a chart:
every 4H breakout it found, every single candle liquidity pool it
armed, which candle swept each pool, which key level price rejected
from, and whether an H1 confirmation followed.

This exists to be checked BY HAND against a chart. Aggregate R tables
say whether the engine made money; they cannot say whether it is
reading the chart the way a person reads it. Only a list of times and
prices you can pull up on TradingView can answer that (operator,
2026-09-16: "Give me samples of what the bot is seeing as 4H breakout
and a single candle liquidity. Give me the timing... let me manually
check it").

Every line is a claim you can falsify by looking. That is the point.

Usage (VPS):
    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.show_setups --instruments GBPUSD,USDCHF \\
        --from 2026-09-07 --to 2026-09-17
"""

from __future__ import annotations

import argparse
import bisect
import sys

import pandas as pd

from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..engine.bias import detect_confirmations
from ..engine.candles import load_candles
from ..engine.key_levels import detect_key_levels
from ..engine.structure import Direction
from ..engine.runner import (
    _find_liquidity_setups, _find_entry_candidates, _trim_to_recent_years,
)


def _fmt(p, digits):
    return f"{p:.{digits}f}"


def _digits(instrument):
    return 2 if any(x in instrument for x in ("JPY", "XAU", "US30", "NAS", "JP225", "OIL")) else 5


def report(instrument, source, start, end, years, mode, n=2):
    h4 = load_candles(source, instrument, "H4")
    h1 = load_candles(source, instrument, "H1")
    # A trailing window, not full history: this is a read-the-chart aid,
    # and the structure that matters for last week formed recently. Say
    # so rather than implying it matches what the live bot (which loads
    # far more) computes.
    h4 = _trim_to_recent_years(h4, years)
    h1 = _trim_to_recent_years(h1, years)
    if not h4:
        print(f"{instrument}: no H4 data")
        return

    d = _digits(instrument)
    confs = sorted(detect_confirmations(h4, n), key=lambda c: c.time)
    levels = detect_key_levels(h4, n)
    setups = _find_liquidity_setups(h4, confs, levels, n, liquidity_mode=mode)
    candidates = _find_entry_candidates(h1, setups)
    by_setup = {}
    for c in candidates:
        by_setup.setdefault(c.setup_id, []).append(c)

    h4_times = [c.time for c in h4]

    print()
    print("=" * 72)
    print(f"{instrument}   {start.date()} .. {end.date()}   (mode: {mode})")
    print("=" * 72)

    window = [c for c in confs if start <= c.time <= end]
    print()
    print(f"4H BREAKOUTS the engine found  ({len(window)} in this window)")
    if not window:
        print("   none")
    for c in window:
        i = bisect.bisect_left(h4_times, c.time)
        bar = h4[i] if i < len(h4) and h4[i].time == c.time else None
        shape = (f"  candle o {_fmt(bar.open, d)}  h {_fmt(bar.high, d)}  "
                 f"l {_fmt(bar.low, d)}  c {_fmt(bar.close, d)}") if bar else ""
        kind = str(getattr(c, "kind", "")).split(".")[-1].lower()
        print(f"   {c.time}  {c.direction.value:<8} {kind:<12}{shape}")

    in_window = [s for s in setups if start <= s.liquidity_time <= end]

    # Grouped by the 4H candle that did the sweeping, not listed per pool.
    # When one candle takes a stack of lows it is ONE event on the chart,
    # and printing it once per pool made a single XAUUSD sweep appear
    # seven times -- unreadable, and it misrepresents what happened.
    groups = {}
    for s in in_window:
        groups.setdefault((s.sweep_from, s.direction), []).append(s)

    print()
    print(f"SINGLE CANDLE LIQUIDITY  ({len(groups)} sweep events, "
          f"{len(in_window)} pools)")
    if not groups:
        print("   none")

    for (sweep_time, direction), items in sorted(groups.items(), key=lambda kv: str(kv[0][0])):
        side = "low" if direction == Direction.BULLISH else "high"
        i = bisect.bisect_left(h4_times, sweep_time)
        bar = h4[i] if i < len(h4) and h4[i].time == sweep_time else None
        print()
        print(f"   4H CANDLE {sweep_time}  swept {direction.value} liquidity")
        if bar:
            print(f"      that candle:  o {_fmt(bar.open, d)}  h {_fmt(bar.high, d)}  "
                  f"l {_fmt(bar.low, d)}  c {_fmt(bar.close, d)}")
        print(f"      took the {side} of {len(items)} earlier 4H candle(s):")
        for s in sorted(items, key=lambda s: s.liquidity_time):
            print(f"         {_fmt(s.liquidity_price, d)}   4H CANDLE {s.liquidity_time}")

        brk = sorted({s.breakout_time for s in items})
        print(f"      armed by the 4H breakout at {', '.join(str(b) for b in brk)}")

        if items[0].h4_validated:
            lvl = items[0].reaction_level_candidates[0]
            rel = "above" if lvl.price > items[0].liquidity_price else "below"
            print(f"      KEY LEVEL {_fmt(lvl.price, d)}   4H CANDLE {lvl.time}  "
                  f"({lvl.shape}, sits {rel} the pool)")

        got = [c for s in items for c in by_setup.get(s.setup_id, [])]
        if got:
            for c in sorted(got, key=lambda c: c.index):
                print(f"      H1 confirmation  {h1[c.index].time}  ({c.trigger})")
        else:
            print("      no H1 confirmation -- nothing was taken")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instruments", required=True, help="comma-separated, or ALL")
    ap.add_argument("--source", default="dukascopy")
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--years", type=float, default=1.0,
                    help="how much trailing history to load for structure (default 1)")
    ap.add_argument("--mode", default="single_candle_h4",
                    choices=("swing", "single_candle", "single_candle_h4"))
    args = ap.parse_args()

    sys.stdout.reconfigure(line_buffering=True)
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(days=1)

    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]

    for instrument in instruments:
        try:
            report(instrument, args.source, start, end, args.years, args.mode)
        except FileNotFoundError:
            print(f"{instrument}: no cached data")

    print()
    print("Times are UTC. Set your TradingView chart to UTC before comparing,")
    print("or the candles will not line up with these.")


if __name__ == "__main__":
    main()
