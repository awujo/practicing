"""
The whole shipped system against the whole taught one.

Every other comparison tool here moves one lever. This moves all of
them at once, because "is the new system any good" is a different
question from "which part of it did the work", and it deserves to be
asked first: if the whole thing is no better than what ships today,
decomposing it is wasted VPS time.

    shipped   what the bots run. is_engulfing + fourth_man, target
              min(3R, ERL), Daily must break out.

    taught    TRIGGERS_TAUGHT (sweep_break, breakout, disrespect,
              fourth_man), target = the external liquidity, and the
              bias caveat: a Daily that only REJECTED counts when the
              Weekly also rejected and H4 carries the breakout.

WHAT IS AND IS NOT IN "TAUGHT", AND WHY
---------------------------------------
Three things are in because the source states them as the rule:

  triggers      Bishop enumerates four and rates breakout and
                sweep+break highest: "if you have these two, [missing
                it] is a missed entry" (entries-part5 t=410-431).
  erl target    Seven separate statements that the target IS the
                liquidity, no counter-evidence. His own finished trades
                read 3.4R to almost 7R.
  bias caveat   He takes those trades live, on XAUUSD and EURUSD
                (bias-1 t=1845-1890, t=1305-1335).

Two things are OUT of the default, deliberately:

  require_qmr   4th man plays QMR levels, but "I love to play..." is a
                preference, not a gate, and Bishop -- who is the
                implementation authority here, per the operator's own
                division of labour -- never gates on QMR at all. It is
                4th man's vocabulary, not Bishop's system.
  imbalance     Same shape of argument, and the one existing
                measurement is against it (46.3% win vs 51.7%, 0.786
                R/trade vs 0.990, 2026-09-02 -- on the pre-fix engine,
                so it settles nothing).

Both are available as variants rather than being silently folded in.
Calling a preference a rule is how a system stops being the one that
was taught.

USAGE
-----
    docker exec -d -u abc -w /config/trading mt5 sh -c \\
        'nice -n 19 python3 -m backtest.tools.compare_systems \\
            --instruments ALL > /config/ab_systems.log 2>&1'

Add --variants qmr,imbalance to also run those filters on top of
taught. Each variant is another full pass per instrument, so on a
machine also running the live bots expect it to take proportionally
longer.

READ THE TRIGGER BREAKDOWN FIRST. This repo has twice drawn the wrong
conclusion from a headline: the 2026-09-02 A/B read as a verdict on
stops when it had measured "take only plug-and-play trades", and the
taught triggers were silently disabled by a touch gate until
2026-09-22. A breakdown of which code path produced each trade is the
thing that catches both.

Per-trade CSVs go to backtest/results/ so later questions do not need
another run. Read them with summarize_results.
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

SHIPPED = {}

TAUGHT = {
    "confirmation_triggers": TRIGGERS_TAUGHT,
    "erl_mode": "target",
    "bias_caveat": True,
}

VARIANTS = {
    "qmr": {"require_qmr": True},
    "imbalance": {"require_imbalance_overlap": True},
}


def _run(instrument, overrides, args):
    return run_backtest(
        instrument, args.entry_style,
        avoid_rollover_entries=not args.no_avoid_rollover,
        min_reward_r=args.min_reward_r,
        origin_kind=args.origin_kind,
        close_based_sweep_break=not args.wick_based_sweep_break,
        stop_anchor=args.stop_anchor,
        **overrides,
    )


def _dump(records, instrument, mode, args):
    if not args.dump_trades:
        return
    os.makedirs(args.dump_trades, exist_ok=True)
    # "taught+qmr" -> "_taught_qmr". A '+' in a filename sorts before
    # '.' so it reorders a directory listing oddly, and it is one more
    # character to quote correctly in every shell that later touches
    # these files.
    suffix = "" if mode == "shipped" else "_" + mode.replace("+", "_")
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
    return (f"{label:<11} {s['n']:>5} trades  {s['win']:>5.1f}% win  "
            f"{s['total']:>9.1f}R  {s['per']:>6.2f} R/trade  {s['avg_win']:>5.2f} avgWin")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True,
                        help="comma-separated, or ALL")
    parser.add_argument("--entry-style", default="conservative",
                        choices=("aggressive", "conservative"))
    parser.add_argument("--variants", default="",
                        help=f"comma-separated extras on top of taught: "
                             f"{','.join(VARIANTS)}. Each is another full pass.")
    parser.add_argument("--stop-anchor", default=LIVE_LAUNCH_FLAGS["stop_anchor"])
    parser.add_argument("--min-reward-r", type=float,
                        default=LIVE_FIXED_FLAGS["min_reward_r"])
    parser.add_argument("--no-avoid-rollover", action="store_true")
    parser.add_argument("--origin-kind", default=LIVE_LAUNCH_FLAGS["origin_kind"],
                        choices=("sweep_break", "any"))
    parser.add_argument("--wick-based-sweep-break", action="store_true")
    parser.add_argument("--dump-trades", default="backtest/results")
    args = parser.parse_args()

    modes = {"shipped": SHIPPED, "taught": TAUGHT}
    for name in [v.strip() for v in args.variants.split(",") if v.strip()]:
        if name not in VARIANTS:
            parser.error(f"unknown variant {name!r}; choose from {','.join(VARIANTS)}")
        modes[f"taught+{name}"] = {**TAUGHT, **VARIANTS[name]}

    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]

    print("shipped  triggers=%s  erl_mode=cap  bias_caveat=False" % (TRIGGERS_SHIPPED,))
    print("taught   triggers=%s  erl_mode=target  bias_caveat=True" % (TRIGGERS_TAUGHT,))
    for name in modes:
        if name.startswith("taught+"):
            print(f"{name:<9} + {VARIANTS[name.split('+')[1]]}")
    print(f"flags: entry_style={args.entry_style}  origin_kind={args.origin_kind}  "
          f"stop_anchor={args.stop_anchor}  min_reward_r={args.min_reward_r}  "
          f"avoid_rollover_entries={not args.no_avoid_rollover}", flush=True)
    print(flush=True)

    totals = {m: {"n": 0, "r": 0.0, "wins": 0, "by_trigger": Counter()} for m in modes}

    for instrument in instruments:
        per_mode = {}
        failed = False
        for mode, overrides in modes.items():
            t0 = time.time()
            try:
                recs = _run(instrument, overrides, args)
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
        for mode in modes:
            s, secs = per_mode[mode]
            totals[mode]["n"] += s["n"]
            totals[mode]["r"] += s["total"]
            totals[mode]["wins"] += round(s["win"] * s["n"] / 100.0)
            totals[mode]["by_trigger"] += s["by_trigger"]
            print(f"  {_row(mode, s)}  [{secs:.0f}s]", flush=True)
            breakdown = ", ".join(f"{k}={v}" for k, v in sorted(s["by_trigger"].items()))
            print(f"  {'':<11} {breakdown or '(no trades)'}", flush=True)
        a, b = per_mode["shipped"][0], per_mode["taught"][0]
        print(f"  {'delta':<11} {b['n']-a['n']:>+5} trades  {b['win']-a['win']:>+5.1f}% win  "
              f"{b['total']-a['total']:>+9.1f}R  {b['per']-a['per']:>+6.2f} R/trade", flush=True)
        print(flush=True)

    print("=" * 78)
    print("POOLED, ALL INSTRUMENTS")
    for mode in modes:
        t = totals[mode]
        win = (100.0 * t["wins"] / t["n"]) if t["n"] else 0.0
        per = (t["r"] / t["n"]) if t["n"] else 0.0
        net = per - 0.12
        print(f"  {mode:<11} {t['n']:>6} trades  {win:>5.1f}% win  {t['r']:>9.1f}R  "
              f"{per:>6.2f} R/trade  {net:>6.2f} net")
        for k, v in sorted(t["by_trigger"].items(), key=lambda kv: -kv[1]):
            share = (100.0 * v / t["n"]) if t["n"] else 0.0
            print(f"      {k:<16} {v:>6}  ({share:>4.1f}%)")

    print()
    print("  net subtracts a flat 0.12R per round trip for spread, which the")
    print("  engine does not model. It is an assumption, not a measurement.")
    print()
    print("  Read the trigger breakdown before the R column. The taught set has")
    print("  four patterns against two and should find MORE setups; if it found")
    print("  fewer, something is filtering rather than matching and the R")
    print("  numbers are not answering the question that was asked.")


if __name__ == "__main__":
    main()
