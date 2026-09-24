"""
A/B the shipped confirmation triggers against the taught ones.

This is the big one. Everything else measured a parameter; this
measures whether the entry patterns the engine looks for are the ones
the course teaches.

  shipped  is_engulfing + fourth_man. `is_engulfing()` is a classic
           candlestick engulfing: prev bearish, curr bullish, curr's
           body covering prev's. That pattern appears nowhere in either
           course.

  taught   sweep_break + breakout + open_close + fourth_man, in Bishop's
           own order of preference. "Engulfing" in the source means an
           ENGULFED OPEN-CLOSE KEY LEVEL -- two same-direction candles
           form a level, a later candle closes through it, price returns
           to it, and the return is the entry (SLK_SPEC 5.2). The
           breakout and sweep+break are the two he rates above all the
           rest: "if you have these two, [missing it] is a missed entry"
           (bishop-entries-part5 t=410-431).

Read SLK_SPEC.md sections 5.1-5.5 before interpreting anything here.

WHAT TO LOOK AT, in order:

1. **The trigger breakdown**, not the headline. This repo has already
   been burned once by reading a headline: the 2026-09-02 A/B looked
   like a heavy loss for zone-anchored stops, and the `stop_kind`
   breakdown showed every surviving trade was `plug_and_play_zone` --
   the run had measured "take only plug-and-play trades", a question
   nobody asked. OPERATIONS_LOG's own conclusion was "keep emitting a
   breakdown of which code path actually produced each result". So the
   per-trigger counts print first and are the thing to read.

2. **Trade count.** The taught set has four triggers against two, so it
   should find MORE setups, not fewer. If it finds fewer, something is
   filtering rather than matching and the R numbers are meaningless.

3. R/trade, last.

Usage (VPS):

    docker exec -d -u abc -w /config/trading mt5 sh -c \\
        'nice -n 19 python3 -m backtest.tools.compare_triggers \\
            --instruments ALL > /config/ab_triggers.log 2>&1'

Per-trade CSVs are written to backtest/results/ as it goes, so later
questions can be asked without repeating the run. Read them with
summarize_results.

Flags come from live_flags.py -- what the bots actually launch with --
not from run_backtest's dataclass defaults. Measuring a configuration
nobody flies was review finding 8 and it has bitten twice.
"""

from __future__ import annotations

import argparse
import os
import time
import traceback
from collections import Counter

from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..engine.runner import TRIGGERS_SHIPPED, TRIGGERS_TAUGHT, run_backtest
from ..engine.trade_log import write_trade_log
from .live_flags import LIVE_FIXED_FLAGS, LIVE_LAUNCH_FLAGS

MODES = {"shipped": TRIGGERS_SHIPPED, "taught": TRIGGERS_TAUGHT}


def _run(instrument, triggers, args):
    return run_backtest(
        instrument, args.entry_style,
        confirmation_triggers=triggers,
        avoid_rollover_entries=not args.no_avoid_rollover,
        min_reward_r=args.min_reward_r,
        origin_kind=args.origin_kind,
        close_based_sweep_break=not args.wick_based_sweep_break,
        stop_anchor=args.stop_anchor,
    )


def _dump(records, instrument, mode, args):
    if not args.dump_trades:
        return
    os.makedirs(args.dump_trades, exist_ok=True)
    suffix = "" if mode == "shipped" else "_taughttriggers"
    write_trade_log(records, os.path.join(
        args.dump_trades, f"{instrument}_{args.entry_style}{suffix}.csv"))


def _stats(recs):
    closed = [r for r in recs if r.exit_reason in ("target_hit", "stop_hit")
              and r.r_multiple is not None]
    wins = [r for r in closed if r.exit_reason == "target_hit"]
    total = sum(r.r_multiple for r in closed)
    n = len(closed)
    return {
        "n": n,
        "win": (100.0 * len(wins) / n) if n else 0.0,
        "total": total,
        "per": (total / n) if n else 0.0,
        "avg_win": (sum(r.r_multiple for r in wins) / len(wins)) if wins else 0.0,
        "by_trigger": Counter(r.trigger_type for r in closed),
    }


def _row(label, s):
    return (f"{label:<9} {s['n']:>5} trades  {s['win']:>5.1f}% win  "
            f"{s['total']:>9.1f}R  {s['per']:>6.2f} R/trade  {s['avg_win']:>5.2f} avgWin")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True,
                        help="comma-separated, or ALL")
    parser.add_argument("--entry-style", default="conservative",
                        choices=("aggressive", "conservative"))
    parser.add_argument("--stop-anchor", default=LIVE_LAUNCH_FLAGS["stop_anchor"])
    parser.add_argument("--min-reward-r", type=float,
                        default=LIVE_FIXED_FLAGS["min_reward_r"])
    parser.add_argument("--no-avoid-rollover", action="store_true")
    parser.add_argument("--origin-kind", default=LIVE_LAUNCH_FLAGS["origin_kind"],
                        choices=("sweep_break", "any"))
    parser.add_argument("--wick-based-sweep-break", action="store_true",
                        help="turn OFF close-based sweep breaks, which the live bots "
                             "run WITH and which is therefore the default here")
    parser.add_argument("--dump-trades", default="backtest/results",
                        help="directory for per-trade CSVs; blank disables")
    args = parser.parse_args()

    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]

    print(f"shipped = {TRIGGERS_SHIPPED}")
    print(f"taught  = {TRIGGERS_TAUGHT}")
    print(f"flags: entry_style={args.entry_style}  origin_kind={args.origin_kind}  "
          f"close_based_sweep_break={not args.wick_based_sweep_break}  "
          f"stop_anchor={args.stop_anchor}  min_reward_r={args.min_reward_r}  "
          f"avoid_rollover_entries={not args.no_avoid_rollover}", flush=True)
    print(flush=True)

    totals = {m: {"n": 0, "r": 0.0, "wins": 0, "by_trigger": Counter()} for m in MODES}

    for instrument in instruments:
        per_mode = {}
        failed = False
        for mode, triggers in MODES.items():
            t0 = time.time()
            try:
                recs = _run(instrument, triggers, args)
                _dump(recs, instrument, mode, args)
                per_mode[mode] = (_stats(recs), time.time() - t0)
            except FileNotFoundError:
                print(f"{instrument:<9} no cached data, skipped", flush=True)
                failed = True
                break
            except Exception:
                print(f"{instrument:<9} {mode} FAILED:", flush=True)
                traceback.print_exc()
                failed = True
                break
        if failed:
            continue

        print(f"{instrument}", flush=True)
        for mode in MODES:
            s, secs = per_mode[mode]
            totals[mode]["n"] += s["n"]
            totals[mode]["r"] += s["total"]
            totals[mode]["wins"] += round(s["win"] * s["n"] / 100.0)
            totals[mode]["by_trigger"] += s["by_trigger"]
            print(f"  {_row(mode, s)}  [{secs:.0f}s]", flush=True)
            breakdown = ", ".join(f"{k}={v}" for k, v in sorted(s["by_trigger"].items()))
            print(f"  {'':<9} triggers: {breakdown or '(none)'}", flush=True)
        a, b = per_mode["shipped"][0], per_mode["taught"][0]
        print(f"  {'delta':<9} {b['n']-a['n']:>+5} trades  {b['win']-a['win']:>+5.1f}% win  "
              f"{b['total']-a['total']:>+9.1f}R  {b['per']-a['per']:>+6.2f} R/trade", flush=True)
        print(flush=True)

    print("=" * 78)
    print("POOLED, ALL INSTRUMENTS")
    for mode in MODES:
        t = totals[mode]
        win = (100.0 * t["wins"] / t["n"]) if t["n"] else 0.0
        per = (t["r"] / t["n"]) if t["n"] else 0.0
        print(f"  {mode:<9} {t['n']:>6} trades  {win:>5.1f}% win  {t['r']:>9.1f}R  "
              f"{per:>6.2f} R/trade")
        for k, v in sorted(t["by_trigger"].items(), key=lambda kv: -kv[1]):
            share = (100.0 * v / t["n"]) if t["n"] else 0.0
            print(f"      {k:<16} {v:>6}  ({share:>4.1f}%)")

    ns, nt = totals["shipped"]["n"], totals["taught"]["n"]
    if ns and nt:
        print()
        print(f"  net: {totals['taught']['r']/nt - totals['shipped']['r']/ns:+.3f} "
              f"R/trade for the taught triggers")
        print()
        print("  Read the trigger breakdown before the R numbers. The taught set")
        print("  has four patterns against two, so it should find MORE setups. If")
        print("  it found fewer, something is filtering rather than matching and")
        print("  the R column is not answering the question that was asked.")


if __name__ == "__main__":
    main()
