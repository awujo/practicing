"""
A/B the two readings of the external-liquidity target, on real history.

The engine ships `target = min(3R, ERL)`. The course videos say the
target IS the external liquidity, with no ceiling above it. Seven
separate statements, no counter-evidence (citations in
knowledge-base/STRATEGY_VS_IMPLEMENTATION.md, "Targets"):

    "Once the external liquidity is taken, expect a reversal. So the
    target should always be external liquidity."   bias-entries t=330

    "There was no logical reason for you holding all the way past this
    liquidity, because this is an external liquidity. Price tends to
    reverse."                                     breakdown-2 t=615

The R multiples he reads off finished trades run 3.4R, 3.6R, 4R, 5R,
5.6R, 5.9R, 6R, "almost 7R". None is a number he chose; each is what the
distance to liquidity was worth. `min(3R, ERL)` truncates all of them.

The two modes are IDENTICAL on every trade whose ERL is nearer than 3R,
so the comparison is not "which strategy" -- it is one question about
one subset of trades:

    when the liquidity is further away than 3R, is it better to take
    the 3R or to hold for the liquidity?

Holding wins more R per winner and loses more winners to a stop that
would otherwise have been a 3R win. Which effect dominates is exactly
what cannot be reasoned out, hence this.

The `capped` column bounds the whole question: trades where the two
modes agree cannot contribute to the difference, and a small capped
count means a small possible effect however the rest reads.

Usage (VPS -- real cached data required, this repo checkout has none):

    docker exec -u abc -w /config/trading mt5 nice -n 19 python3 \\
        -m backtest.tools.compare_erl_target --instruments ALL

Add --entry-style aggressive to see the other deployed bot. Everything
else is pinned to live_flags.py, i.e. to what the bots actually run,
rather than to run_backtest's dataclass defaults -- measuring a
configuration nobody flies was review finding 8 and it has bitten twice.
"""

from __future__ import annotations

import argparse
import time
import traceback

from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..engine.runner import run_backtest
from .live_flags import LIVE_FIXED_FLAGS, LIVE_LAUNCH_FLAGS

MODES = ("cap", "target")


def _run(instrument, erl_mode, args):
    return run_backtest(
        instrument, args.entry_style,
        erl_mode=erl_mode,
        avoid_rollover_entries=not args.no_avoid_rollover,
        min_reward_r=args.min_reward_r,
        origin_kind=args.origin_kind,
        close_based_sweep_break=not args.wick_based_sweep_break,
        stop_anchor=args.stop_anchor,
    )


def _stats(recs):
    """Closed trades only. `capped` counts the trades where the two
    modes can possibly differ -- under "cap" it is the count that were
    truncated, under "target" the count that were extended."""
    closed = [r for r in recs if r.exit_reason in ("target_hit", "stop_hit")
              and r.r_multiple is not None]
    wins = [r for r in closed if r.exit_reason == "target_hit"]
    total_r = sum(r.r_multiple for r in closed)
    n = len(closed)
    return {
        "n": n,
        "win_pct": (100.0 * len(wins) / n) if n else 0.0,
        "total_r": total_r,
        "per_trade": (total_r / n) if n else 0.0,
        "capped": sum(1 for r in closed if r.erl_capped),
        "avg_win": (sum(r.r_multiple for r in wins) / len(wins)) if wins else 0.0,
    }


def _row(label, s):
    return (f"{label:<8} {s['n']:>5} trades  {s['win_pct']:>5.1f}% win  "
            f"{s['total_r']:>9.1f}R  {s['per_trade']:>6.2f} R/trade  "
            f"{s['avg_win']:>5.2f} avgWin  {s['capped']:>5} capped")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True,
                        help="comma-separated, or ALL for every Dukascopy instrument")
    parser.add_argument("--entry-style", default="conservative",
                        choices=("aggressive", "conservative"))
    parser.add_argument("--stop-anchor", default=LIVE_LAUNCH_FLAGS["stop_anchor"])
    parser.add_argument("--min-reward-r", type=float,
                        default=LIVE_FIXED_FLAGS["min_reward_r"])
    parser.add_argument("--no-avoid-rollover", action="store_true")
    parser.add_argument("--origin-kind", default=LIVE_LAUNCH_FLAGS["origin_kind"],
                        choices=("sweep_break", "any"))
    # Inverted for consistency with compare_liquidity_modes, where the
    # name is load-bearing for saved command lines. The live bots run
    # WITH close-based sweep breaks, so this flag turns the deployed
    # behaviour OFF.
    parser.add_argument("--wick-based-sweep-break", action="store_true",
                        help="turn OFF close-based sweep breaks, which the live bots "
                             "run WITH and which is therefore the default here")
    args = parser.parse_args()

    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]

    print(f"flags: entry_style={args.entry_style}  origin_kind={args.origin_kind}  "
          f"close_based_sweep_break={not args.wick_based_sweep_break}  "
          f"stop_anchor={args.stop_anchor}  min_reward_r={args.min_reward_r}  "
          f"avoid_rollover_entries={not args.no_avoid_rollover}", flush=True)
    print(flush=True)

    totals = {m: {"n": 0, "r": 0.0, "wins": 0, "capped": 0} for m in MODES}

    for instrument in instruments:
        per_mode = {}
        failed = False
        for mode in MODES:
            t0 = time.time()
            try:
                per_mode[mode] = (_stats(_run(instrument, mode, args)), time.time() - t0)
            except FileNotFoundError:
                print(f"{instrument:<9} no cached data, skipped", flush=True)
                failed = True
                break
            except Exception:
                print(f"{instrument:<9} erl_mode={mode} FAILED:", flush=True)
                traceback.print_exc()
                failed = True
                break
        if failed:
            continue

        print(f"{instrument}", flush=True)
        for mode in MODES:
            s, secs = per_mode[mode]
            totals[mode]["n"] += s["n"]
            totals[mode]["r"] += s["total_r"]
            totals[mode]["wins"] += round(s["win_pct"] * s["n"] / 100.0)
            totals[mode]["capped"] += s["capped"]
            print(f"  {_row(mode, s)}  [{secs:.0f}s]", flush=True)
        c, t = per_mode["cap"][0], per_mode["target"][0]
        print(f"  {'delta':<8} {t['n']-c['n']:>+5} trades  "
              f"{t['win_pct']-c['win_pct']:>+5.1f}% win  "
              f"{t['total_r']-c['total_r']:>+9.1f}R  "
              f"{t['per_trade']-c['per_trade']:>+6.2f} R/trade  "
              f"{t['avg_win']-c['avg_win']:>+5.2f} avgWin", flush=True)
        print(flush=True)

    print("=" * 78)
    print("POOLED, ALL INSTRUMENTS")
    for mode in MODES:
        t = totals[mode]
        win = (100.0 * t["wins"] / t["n"]) if t["n"] else 0.0
        per = (t["r"] / t["n"]) if t["n"] else 0.0
        print(f"  {mode:<8} {t['n']:>6} trades  {win:>5.1f}% win  {t['r']:>9.1f}R  "
              f"{per:>6.2f} R/trade  {t['capped']:>5} capped")
    n_c, n_t = totals["cap"]["n"], totals["target"]["n"]
    if n_c and n_t:
        d = totals["target"]["r"] / n_t - totals["cap"]["r"] / n_c
        print()
        print(f"  net: {d:+.3f} R/trade for targeting the liquidity")
        print(f"  {totals['cap']['capped']} of {n_c} trades were truncated by the cap "
              f"({100.0*totals['cap']['capped']/n_c:.0f}%) -- the rest are identical "
              f"under both modes and cannot move this number.")
    print()
    print("  Expect the win rate to FALL and avgWin to RISE. The question is")
    print("  only which one wins, and R/trade is the column that answers it.")


if __name__ == "__main__":
    main()
