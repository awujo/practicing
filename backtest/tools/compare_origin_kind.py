"""
A/B across two independent line-chart-vs-wick questions the engine had
gotten inconsistent about, both raised directly by the operator on
2026-09-13:

  1. origin_kind: does bootstrapping the first Daily/Weekly bias from
     EITHER a plain breakout OR a sweep+break ("any") change overall
     performance, versus requiring the stricter sweep+break alone (the
     long-standing default, "sweep_break")? bias.py's own module
     docstring already says a confirmation should accept either shape
     ("both are valid"), but run_backtest()'s origin bootstrap only
     accepted the stricter one.

  2. close_based_sweep_break: for a sweep+break specifically, is the
     LEVEL a break is measured against read off the swing candle's
     WICK (the long-standing default, False) or its CLOSE (True,
     matching how the plain-breakout half already works via
     close_based_breakout, and the source material's own stated
     preference for verifying a break off the line chart)? The sweep
     itself stays wick-based either way -- only the break level differs.

Rather than assume either "fix" is strictly better for being more
permissive/more consistent, this runs all four combinations across full
history and reports total R / win rate for each -- a different bootstrap
direction or break level can cascade into different trades for the WHOLE
backtest, not just the window-size question compare_history_window.py is
answering separately.

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
CLOSE_BASED_SWEEP_BREAK_OPTIONS = (False, True)


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

    print(f"{'origin_kind':>12}  {'close_sweep_break':>18}  {'trades':>6}  {'win%':>6}  "
          f"{'totalR':>8}  {'avgR':>6}", flush=True)
    start = time.monotonic()
    for kind in ORIGIN_KINDS:
        for close_based in CLOSE_BASED_SWEEP_BREAK_OPTIONS:
            all_records = []
            for instrument in instruments:
                records = run_backtest(instrument, common_kwargs["entry_style"],
                                        avoid_rollover_entries=common_kwargs["avoid_rollover_entries"],
                                        min_reward_r=common_kwargs["min_reward_r"],
                                        stop_anchor=common_kwargs["stop_anchor"],
                                        origin_kind=kind, close_based_sweep_break=close_based)
                all_records.extend(records)
                elapsed = time.monotonic() - start
                print(f"# [{elapsed / 60:6.1f}m elapsed] origin_kind={kind} "
                      f"close_based_sweep_break={close_based}: {instrument} done ({len(records)} trades)",
                      flush=True)

            stats = summarize(all_records)
            win_pct = f"{stats['win_rate'] * 100:.1f}%" if stats["win_rate"] is not None else "n/a"
            avg_r = f"{stats['avg_r']:.3f}" if stats["avg_r"] is not None else "n/a"
            print(f"{kind:>12}  {str(close_based):>18}  {stats['total_trades']:>6}  {win_pct:>6}  "
                  f"{stats['total_r']:>8.1f}  {avg_r:>6}", flush=True)


if __name__ == "__main__":
    main()
