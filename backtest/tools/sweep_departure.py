"""
Sweep `min_departure_r` at finer resolution than the 2026-09-02 spot-check.

Motivation (operator, 2026-09-12): after the departure-gate feature went
live on bot2, the operator pushed back hard on requiring a full 1.0R travel
before a limit order rests at all -- their read from experience is that a
lot of real "sniper" entries retrace on the very next candle, well under
1R away, and a full-1R requirement would refuse to even place the order
for those. That is a real, specific, checkable claim, not a vibe -- so
check it rather than assert either side from memory.

The 2026-09-02 log entry (bot/OPERATIONS_LOG.md) only sampled four points
(0.0, 0.5, 1.0, 1.5), all under trigger_wick's OLD stop anchor pairing.
This resamples the same methodology (aggressive style, cancel at 80%,
avoid_rollover_entries=True, min_reward_r=1.0 -- exactly what
orchestrator.py's run_backtest() call actually uses) at a finer grid so a
middle ground between "immediate" and "a full 1R" can be read off the
table rather than guessed.

Usage (on the VPS, where the real cached candle data lives -- this repo
checkout has no cached CSVs, only .lock files, so running it here produces
nothing):

    docker exec -u abc -w /config/trading mt5 python3 -m backtest.tools.sweep_departure \\
        --instruments $(grep -oP '(?<=--instruments )\\S+' /srv/slk-bot/launch_bot2.sh) \\
        --stop-anchor trigger_wick
"""

from __future__ import annotations

import argparse
import statistics

from ..engine.runner import run_backtest
from ..engine.trade_log import summarize

DEFAULT_VALUES = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def sweep(instruments: list[str], entry_style: str, stop_anchor: str,
          cancel_at: float, min_reward_r: float, avoid_rollover: bool,
          values: list[float], start_date=None, end_date=None) -> list[dict]:
    rows = []
    for v in values:
        all_records = []
        for instrument in instruments:
            records = run_backtest(
                instrument, entry_style,
                avoid_rollover_entries=avoid_rollover,
                min_reward_r=min_reward_r,
                stop_anchor=stop_anchor,
                entry_fill="limit",
                cancel_at_target_fraction=cancel_at,
                min_departure_r=v,
                start_date=start_date, end_date=end_date,
            )
            all_records.extend(records)

        stats = summarize(all_records)
        closed = [r for r in all_records if r.status in ("closed_win", "closed_loss", "closed_breakeven")]
        med_stop = statistics.median(r.risk_pips for r in closed) if closed else None
        rows.append({
            "departure": v,
            "trades": stats["total_trades"],
            "win_rate": stats["win_rate"],
            "total_r": stats["total_r"],
            "avg_r": stats["avg_r"],
            "med_stop_pips": med_stop,
        })
    return rows


def _print_table(rows: list[dict]) -> None:
    print(f"{'departure':>9}  {'trades':>6}  {'win%':>6}  {'totalR':>8}  {'avgR':>6}  {'medStop':>8}")
    for row in rows:
        win_pct = f"{row['win_rate'] * 100:.1f}%" if row["win_rate"] is not None else "n/a"
        med_stop = f"{row['med_stop_pips']:.1f}" if row["med_stop_pips"] is not None else "n/a"
        avg_r = f"{row['avg_r']:.3f}" if row["avg_r"] is not None else "n/a"
        print(f"{row['departure']:>9.2f}  {row['trades']:>6}  {win_pct:>6}  "
              f"{row['total_r']:>8.1f}  {avg_r:>6}  {med_stop:>8}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True, help="comma-separated, e.g. EURUSD,GBPUSD,XAUUSD")
    parser.add_argument("--entry-style", default="aggressive", choices=("aggressive", "conservative"))
    parser.add_argument("--stop-anchor", default="trigger_wick", choices=("trigger_wick", "structural"))
    parser.add_argument("--cancel-at", type=float, default=0.8)
    parser.add_argument("--min-reward-r", type=float, default=1.0)
    parser.add_argument("--no-avoid-rollover", action="store_true",
                         help="matches live's actual flag unless passed")
    parser.add_argument("--values", default=",".join(str(v) for v in DEFAULT_VALUES),
                         help="comma-separated min_departure_r values to sweep")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    args = parser.parse_args()

    instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    values = [float(v) for v in args.values.split(",") if v.strip() != ""]

    rows = sweep(
        instruments, args.entry_style, args.stop_anchor,
        args.cancel_at, args.min_reward_r,
        avoid_rollover=not args.no_avoid_rollover,
        values=values, start_date=args.start_date, end_date=args.end_date,
    )
    _print_table(rows)


if __name__ == "__main__":
    main()
