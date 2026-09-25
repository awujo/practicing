"""
Run the SLK system and report how it performs. No A/B, no baseline.

The comparison tools answer "is this better than what we ship". This
answers "is this worth trading", which is a different question and
needs different numbers -- above all DRAWDOWN, which this project has
never measured.

WHY DRAWDOWN IS THE HEADLINE

R/trade alone cannot tell you whether a system is tradeable. 0.30
R/trade across 475 trades a year is roughly 140R a year, which at 0.5%
risk is a very good year -- unless the path to it includes a 40R hole,
in which case 0.5% sizing is a 20% account drawdown and the annual
figure is irrelevant because you would have stopped trading. Every
number this project has produced so far has been an average with no
path attached.

So the report leads with the worst stretch, not the total.

HOW IT IS COMPUTED

Trades are ordered by EXIT time, not entry, and the R curve is walked
once. Drawdown is peak-to-trough on that curve; the losing streak is
the longest run of non-winners. Ordering by exit matters: a trade that
opens early and closes late sits where its result actually landed, and
sorting by entry would show a smoother curve than anyone lived.

Pooled drawdown across instruments assumes you traded all of them
together at equal risk, which is what a portfolio drawdown means. It
is NOT the sum of the per-instrument drawdowns -- those happen at
different times and partly offset.

WHAT IT STILL DOES NOT MODEL

Spread is a flat assumption (see --spread), not a measurement, and
real spreads on indices and crypto are worse than on majors.
Correlation is not modelled at all: 27 instruments is not 27
independent bets, and the EUR pairs and JPY pairs move together, so
the true portfolio risk is higher than a naive reading of these
numbers suggests.

FULL HISTORY OR LIVE WINDOWS

`--windows full` (the default) runs ~20 years per instrument: the
largest sample, and hours of VPS time.

`--windows live` runs the SAME trimmed windows the bot loads from
`bot/history_windows.json`. That is a smaller sample, but it is the
only history the live bot ever sees, so it answers "how will this
behave once deployed" more directly than full history does -- and it
finishes in about half an hour rather than most of a day.

One wrinkle it reports rather than hides: the windows are not equal.
An explicit null in that file means "confirmed NOT safe to cap"
(GBPNZD), so that instrument runs full history while the rest run one
or two years. A pooled equity curve mixing a 20-year series with
26 one-year series is not a portfolio anyone could have traded, so the
pooled figures are also reported over the span every instrument
actually covers.

USAGE

    docker exec -d -u abc -w /config/trading mt5 sh -c \\
        'nice -n 19 python3 -m backtest.tools.run_slk \\
            --instruments ALL > /config/slk.log 2>&1'

    # the deployable-sample answer, in ~30 minutes
    ... -m backtest.tools.run_slk --instruments ALL --windows live

    # with a filter on top, to see whether it earns its place
    ... -m backtest.tools.run_slk --instruments ALL --variant qmr

Per-trade CSVs go to backtest/results/ so later questions do not need
another run.
"""

from __future__ import annotations

import argparse
import os
import time
import traceback
from collections import Counter, defaultdict

from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..engine.runner import run_backtest
from ..engine.trade_log import write_trade_log
# One window resolver, shared with the timing tool, which in turn calls
# the live bot's own. Three copies of this lookup would be three chances
# to measure a machine nobody runs.
from .live_cycle_timing import load_windows
from .slk_system import SLK_VARIANTS, slk_kwargs


def _cost_r(r, spread_pips):
    """What the spread really costs THIS trade, in R.

    A flat charge assumes every trade risks the same distance. They do
    not: measured on real logs the honest mean is ~0.25 R/trade against
    the 0.12 this used to assume, and a trade risking 2 pips on a
    1.5-pip spread pays 0.75R on its own. Cost in R is
    spread_pips/risk_pips, which is what `postmortem` already charges --
    the two tools disagreeing about costs is how a number gets believed
    twice."""
    if not spread_pips:
        return 0.0
    risk = getattr(r, "risk_pips", None)
    if not risk:
        return 0.12
    return spread_pips / risk


def _closed(recs):
    return [r for r in recs if r.exit_reason in ("target_hit", "stop_hit")
            and r.r_multiple is not None]


def _sort_key(r):
    """By EXIT, falling back to entry when a record has no exit time."""
    return (r.exit_time or r.entry_time, r.entry_time)


def _curve_stats(closed, spread):
    """Max drawdown and the longest losing streak, off one walk of the
    R curve in exit order."""
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    streak = 0
    worst_streak = 0
    for r in sorted(closed, key=_sort_key):
        equity += r.r_multiple - _cost_r(r, spread)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if r.exit_reason == "target_hit":
            streak = 0
        else:
            streak += 1
            worst_streak = max(worst_streak, streak)
    return max_dd, worst_streak


def _stats(recs, spread):
    closed = _closed(recs)
    n = len(closed)
    wins = [r for r in closed if r.exit_reason == "target_hit"]
    losses = [r for r in closed if r.exit_reason != "target_hit"]
    total = sum(r.r_multiple for r in closed)
    gross_win = sum(r.r_multiple for r in wins)
    gross_loss = -sum(r.r_multiple for r in losses)
    max_dd, worst_streak = _curve_stats(closed, spread)
    cost_total = sum(_cost_r(r, spread) for r in closed)
    return {
        "n": n,
        "win": (100.0 * len(wins) / n) if n else 0.0,
        "total": total,
        "per": (total / n) if n else 0.0,
        "net": ((total - cost_total) / n) if n else 0.0,
        "cost_total": cost_total,
        "avg_win": (gross_win / len(wins)) if wins else 0.0,
        "avg_loss": (gross_loss / len(losses)) if losses else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf"),
        "max_dd": max_dd,
        "worst_streak": worst_streak,
        "spread": spread,
        "by_trigger": Counter(r.trigger_type for r in closed),
        "closed": closed,
    }


def _report(label, s, width=12):
    # TOTAL R as well as R/trade. A per-trade figure says nothing about
    # how much a year actually produced -- 0.5 R/trade over 20 trades
    # and over 200 trades are different businesses -- and the operator
    # asked for the year's own number, which is this one.
    net_total = s["total"] - s["cost_total"]
    print(f"  {label:<{width}} {s['n']:>5} trades  {s['win']:>5.1f}% win  "
          f"{s['per']:>6.2f} R/trade  {s['net']:>6.2f} net  "
          f"{s['total']:>8.1f}R gross  {net_total:>8.1f}R net  "
          f"PF {s['profit_factor']:>5.2f}  maxDD {s['max_dd']:>7.1f}R  "
          f"streak {s['worst_streak']:>3}", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True, help="comma-separated, or ALL")
    parser.add_argument("--entry-style", default="conservative",
                        choices=("aggressive", "conservative"))
    parser.add_argument("--variant", default="",
                        help=f"one of {','.join(SLK_VARIANTS)}, applied on top")
    parser.add_argument("--entry-fill", default=None,
                        choices=("instant", "limit"),
                        help="'limit' rests the order at the level and fills on "
                             "the RETURN, which is what SLK_SPEC 5.1/5.2 describe: "
                             "'entry is the return to it, not the engulfing "
                             "candle'. 'instant' fills at the confirmation "
                             "candle, which is what every run before 2026-09-25 "
                             "did.")
    parser.add_argument("--honest-fill", action="store_true",
                        help="fill when the signal was KNOWABLE, not when it was "
                             "stamped. classify_entry_pattern() reads candles past "
                             "the entry, so the stamped fill uses information from "
                             "after it. Use this to see what the edge is worth "
                             "without that peek.")
    parser.add_argument("--windows", default="full", choices=("full", "live"),
                        help="'full' runs ~20 years per instrument. 'live' runs "
                             "the trimmed windows the bot actually loads, which "
                             "is a smaller sample but the only one live ever sees.")
    parser.add_argument("--spread", type=float, default=1.5,
                        help="spread in PIPS per round trip, charged against each "
                             "trade's own risk_pips. Still an assumption, but one "
                             "that scales with stop size instead of pretending "
                             "every trade risks the same distance.")
    parser.add_argument("--dump-trades", default="backtest/results")
    args = parser.parse_args()

    extra = {}
    if args.variant:
        if args.variant not in SLK_VARIANTS:
            parser.error(f"unknown variant {args.variant!r}; "
                         f"choose from {','.join(SLK_VARIANTS)}")
        extra = SLK_VARIANTS[args.variant]

    if args.honest_fill:
        extra['fill_at_signal_known'] = True
    if args.entry_fill:
        extra['entry_fill'] = args.entry_fill
    kwargs = slk_kwargs(**extra)
    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]

    window_for = load_windows(instruments=instruments) if args.windows == "live" \
        else (lambda _inst: None)

    print("SLK SYSTEM")
    for k, v in sorted(kwargs.items()):
        print(f"  {k} = {v}")
    print(f"  spread assumption = {args.spread} PIPS/round trip, "
          f"charged per trade as spread/risk_pips")
    print(f"  history = {args.windows}"
          + ("  (bot/history_windows.json, same as live)"
             if args.windows == "live" else "  (~20 years per instrument)"))
    print(flush=True)

    print("PER INSTRUMENT")
    all_closed = []
    first_entry = {}
    for instrument in instruments:
        t0 = time.time()
        try:
            recs = run_backtest(instrument, args.entry_style,
                                max_history_years=window_for(instrument), **kwargs)
        except FileNotFoundError:
            print(f"  {instrument:<12} no cached data, skipped", flush=True)
            continue
        except Exception:
            print(f"  {instrument:<12} FAILED:", flush=True)
            traceback.print_exc()
            continue
        if args.dump_trades:
            os.makedirs(args.dump_trades, exist_ok=True)
            suffix = f"_slk{'_' + args.variant if args.variant else ''}"
            write_trade_log(recs, os.path.join(
                args.dump_trades, f"{instrument}_{args.entry_style}{suffix}.csv"))
        s = _stats(recs, args.spread)
        # Unresolved trades are EXCLUDED from every figure below, so
        # say how many. If a large share never reach stop or target
        # inside MAX_TRADE_DURATION_CANDLES, the reported stats describe
        # the subset that happened to resolve, which is a selection.
        open_n = len(recs) - s["n"]
        all_closed.extend(s["closed"])
        if s["closed"]:
            first_entry[instrument] = min(r.entry_time for r in s["closed"])
        _report(f"{instrument} [{time.time()-t0:.0f}s]", s, width=20)
        if open_n:
            print(f"  {'':<20} {open_n} unresolved and excluded "
                  f"({100.0*open_n/len(recs):.1f}% of {len(recs)})", flush=True)

    if not all_closed:
        print("\nNo closed trades. Nothing to report.")
        return

    print()
    print("BY YEAR (pooled)")
    by_year = defaultdict(list)
    for r in all_closed:
        by_year[str(r.entry_time)[:4]].append(r)
    for year in sorted(by_year):
        _report(year, _stats(by_year[year], args.spread))

    pooled = _stats(all_closed, args.spread)
    print()
    print("=" * 78)
    print("POOLED")
    _report("all", pooled)

    # A pooled equity curve is a claim about a portfolio, so it is only
    # honest over a span the whole portfolio was actually trading. With
    # live windows one instrument can carry twenty years while the rest
    # carry one (GBPNZD's explicit null), and the early part of that
    # curve is a single instrument wearing a portfolio's name -- which
    # flatters the drawdown, because one instrument cannot draw down
    # like twenty-seven can.
    common = _stats([r for r in all_closed if r.entry_time >= max(first_entry.values())],
                    args.spread) if len(first_entry) > 1 else None
    if common and common["n"] and common["n"] != pooled["n"]:
        start = max(first_entry.values())
        latest = max(first_entry, key=lambda i: first_entry[i])
        _report("common span", common)
        print(f"    common span starts {str(start)[:10]}, set by {latest} -- "
              f"{pooled['n'] - common['n']} of {pooled['n']} trades fall before it.")
        print("    Read THIS row as the portfolio result. The 'all' row above")
        print("    includes a stretch when only some instruments had data.")
    print()
    print("  trigger breakdown:")
    for k, v in sorted(pooled["by_trigger"].items(), key=lambda kv: -kv[1]):
        print(f"    {k:<16} {v:>6}  ({100.0*v/pooled['n']:>4.1f}%)")
    print(f"  avg win {pooled['avg_win']:.2f}R   avg loss {pooled['avg_loss']:.2f}R")

    print()
    # Size off the portfolio row, not the flattered one.
    sizing = common if (common and common["n"]) else pooled
    print("  WHAT THE DRAWDOWN MEANS FOR SIZING")
    for risk in (0.25, 0.5, 1.0):
        print(f"    at {risk}% risk/trade: worst stretch is "
              f"{sizing['max_dd'] * risk:.1f}% of the account")
    print()
    print("  Pooled drawdown assumes every instrument traded together at equal")
    print("  risk. It is NOT the sum of the per-instrument figures, which happen")
    print("  at different times and partly offset.")
    print()
    print("  NOT modelled: spread is a flat assumption, and correlation is absent")
    print("  entirely -- 27 instruments is not 27 independent bets, so the real")
    print("  portfolio risk is worse than these numbers read.")


if __name__ == "__main__":
    main()
