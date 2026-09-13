"""
A/B: does bootstrapping the first Daily/Weekly bias from EITHER a plain
breakout OR a sweep+break (origin_kind="any") change overall backtest
performance, versus requiring the stricter sweep+break alone (the
long-standing default)?

Motivation (operator, 2026-09-13): bias.py's own module docstring already
says a confirmation should accept either shape ("EITHER a plain
breakout... OR a sweep+break... both are valid"), but run_backtest()'s
origin bootstrap only accepted the stricter one. Direct question after
that inconsistency surfaced from a GBPJPY history-window failure: rather
than assume "any" is strictly better because it's more permissive, run
both across full history and see the actual difference -- a different
FIRST bias direction changes what BiasCascade replays from, which can
cascade into different trades for the whole backtest, not just the
window-size question compare_history_window.py is answering separately.

Usage (VPS, real cached data required -- this repo checkout has none):
    docker exec -u abc -w /config/trading mt5 nice -n 19 python3 -m backtest.tools.compare_origin_kind \\
        --instruments EURUSD,GBPJPY,US30 --stop-anchor trigger_wick
"""

from __future__ import annotations

import argparse
import time

from ..engine.runner import run_backtest
from ..engine.trade_log import summarize

ORIGIN_KINDS = ("sweep_break", "any")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True, help="comma-separated, e.g. EURUSD,GBPJPY,US30")
    parser.add_argument("--entry-style", default="aggressive", choices=("aggressive", "conservative"))
    parser.add_argument("--stop-anchor", default="trigger_wick", choices=("trigger_wick", "structural"))
    parser.add_argument("--min-reward-r", type=float, default=1.0)
    parser.add_argument("--no-avoid-rollover", action="store_true")
    args = parser.parse_args()

    instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    common_kwargs = dict(avoid_rollover_entries=not args.no_avoid_rollover, min_reward_r=args.min_reward_r,
                          entry_style=args.entry_style, stop_anchor=args.stop_anchor)

    print(f"{'origin_kind':>12}  {'trades':>6}  {'win%':>6}  {'totalR':>8}  {'avgR':>6}", flush=True)
    start = time.monotonic()
    for kind in ORIGIN_KINDS:
        all_records = []
        for instrument in instruments:
            records = run_backtest(instrument, common_kwargs["entry_style"],
                                    avoid_rollover_entries=common_kwargs["avoid_rollover_entries"],
                                    min_reward_r=common_kwargs["min_reward_r"],
                                    stop_anchor=common_kwargs["stop_anchor"],
                                    origin_kind=kind)
            all_records.extend(records)
            elapsed = time.monotonic() - start
            print(f"# [{elapsed / 60:6.1f}m elapsed] origin_kind={kind}: {instrument} done "
                  f"({len(records)} trades)", flush=True)

        stats = summarize(all_records)
        win_pct = f"{stats['win_rate'] * 100:.1f}%" if stats["win_rate"] is not None else "n/a"
        avg_r = f"{stats['avg_r']:.3f}" if stats["avg_r"] is not None else "n/a"
        print(f"{kind:>12}  {stats['total_trades']:>6}  {win_pct:>6}  "
              f"{stats['total_r']:>8.1f}  {avg_r:>6}", flush=True)


if __name__ == "__main__":
    main()
