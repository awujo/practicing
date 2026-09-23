"""
Diagnose a finished run from the per-trade CSVs it already wrote.

A run that took seven hours should not have to be repeated to answer
"why did it lose". `run_slk` and `compare_systems` both dump a full
`TradeRecord` per trade to backtest/results/, and that file carries the
trigger, the target's own geometry, MAE/MFE and the concurrency at
entry. Everything below is read off those columns. Nothing re-runs.

WHAT IT ASKS, AND WHY EACH ONE

  by trigger      Which code path produced the trades, and what each one
                  earned. A pooled R/trade near zero can hide one trigger
                  paying for another's losses, and the fix for that is to
                  drop a trigger, not to abandon the system.

  target geometry With erl_mode="target" the target IS the external
                  liquidity, at whatever distance that sits -- there is
                  no 3R cap. A low win rate is then EXPECTED and not by
                  itself a fault. The question is whether the R:R pays
                  for it, so this reports the distribution of target R
                  and the win rate at each distance.

  the near misses MFE says how far a losing trade got before it turned.
                  If losers routinely reach 3R and then stop out, the
                  target is too far and the money was on the table. This
                  prints an UPPER BOUND on what a cap would have
                  recovered -- upper, because MFE does not say whether
                  the favourable move came before or after the adverse
                  one, so some of those "recovered" trades would have
                  been stopped first.

  spread          The real killer when a system overtrades. Cost scales
                  with trade COUNT while edge scales with R, so this
                  reports the breakeven spread: above it, the system
                  loses on costs alone no matter how sound the entries.

  concurrency     `concurrent_open_positions_at_entry`. If a "0.06
                  R/trade" system holds thirty positions at once, then
                  at 0.5% risk it is risking 15% of the account
                  simultaneously and the per-trade figure is not a
                  portfolio result at all.

USAGE

    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.postmortem --suffix _slk

    # only the instruments that finished
    ... --suffix _slk --instruments EURUSD,GBPJPY
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
from collections import Counter, defaultdict


def _f(row, key):
    """A float, or None when the column is blank. Blank is normal here:
    an open trade has no r_multiple and MAE/MFE are optional."""
    v = (row.get(key) or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load(results_dir, suffix, instruments=None):
    pattern = os.path.join(results_dir, f"*{suffix}.csv")
    rows = []
    files = sorted(glob.glob(pattern))
    for path in files:
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                if instruments and row.get("instrument") not in instruments:
                    continue
                rows.append(row)
    return rows, files


def closed(rows):
    return [r for r in rows
            if r.get("exit_reason") in ("target_hit", "stop_hit")
            and _f(r, "r_multiple") is not None]


def _agg(rows, spread):
    n = len(rows)
    if not n:
        return None
    wins = [r for r in rows if r["exit_reason"] == "target_hit"]
    total = sum(_f(r, "r_multiple") for r in rows)
    return {
        "n": n,
        "win": 100.0 * len(wins) / n,
        "total": total,
        "per": total / n,
        "net": total / n - spread,
        "net_total": total - spread * n,
    }


def _line(label, s, width=16):
    print(f"  {label:<{width}} {s['n']:>6} trades  {s['win']:>5.1f}% win  "
          f"{s['per']:>6.2f} R/trade  {s['net']:>6.2f} net  "
          f"{s['net_total']:>9.1f}R total")


def target_r(row):
    """How far the target sat, in units of the trade's own risk."""
    entry, stop, tgt = (_f(row, "entry_price"), _f(row, "stop_loss"),
                        _f(row, "primary_target"))
    if None in (entry, stop, tgt):
        return None
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    return abs(tgt - entry) / risk


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results-dir", default="backtest/results")
    parser.add_argument("--suffix", default="_slk",
                        help="filename suffix identifying the run, e.g. _slk")
    parser.add_argument("--instruments", default="",
                        help="comma-separated; default is every file found")
    parser.add_argument("--spread", type=float, default=0.12)
    args = parser.parse_args()

    only = {s.strip().upper() for s in args.instruments.split(",") if s.strip()}
    rows, files = load(args.results_dir, args.suffix, only or None)
    if not rows:
        print(f"No CSVs matching *{args.suffix}.csv in {args.results_dir}")
        return
    cl = closed(rows)
    if not cl:
        print(f"{len(rows)} rows, none closed. Nothing to diagnose.")
        return

    print(f"POST-MORTEM  ({len(files)} files, {len(rows)} rows, {len(cl)} closed)")
    print(f"  spread assumption = {args.spread} R/round trip")
    print()

    pooled = _agg(cl, args.spread)
    print("POOLED")
    _line("all", pooled)
    print()

    # 1. Which code path produced the trades, and what each earned.
    print("BY TRIGGER")
    by_trigger = defaultdict(list)
    for r in cl:
        by_trigger[r.get("trigger_type") or "(none)"].append(r)
    for name, group in sorted(by_trigger.items(), key=lambda kv: -len(kv[1])):
        s = _agg(group, args.spread)
        share = 100.0 * s["n"] / pooled["n"]
        _line(f"{name} ({share:.0f}%)", s)
    print()
    print("  A trigger with a positive net column is carrying the ones without.")
    print("  Dropping a losing trigger is a smaller change than abandoning the")
    print("  system, and this is the table that says whether that is available.")
    print()

    # 2. Is the target simply too far away?
    print("BY TARGET DISTANCE  (erl_mode=target sets no cap)")
    buckets = [(0, 2), (2, 3), (3, 5), (5, 8), (8, 12), (12, 1e9)]
    by_bucket = defaultdict(list)
    missing = 0
    for r in cl:
        tr = target_r(r)
        if tr is None:
            missing += 1
            continue
        for lo, hi in buckets:
            if lo <= tr < hi:
                by_bucket[(lo, hi)].append(r)
                break
    for lo, hi in buckets:
        group = by_bucket.get((lo, hi))
        if not group:
            continue
        label = f"{lo}-{hi}R" if hi < 1e9 else f"{lo}R+"
        _line(label, _agg(group, args.spread))
    if missing:
        print(f"  ({missing} trades had no usable target geometry)")
    print()
    print("  A LOW WIN RATE HERE IS NOT BY ITSELF A FAULT. A 10R target is")
    print("  supposed to miss most of the time. Read the net column, not the")
    print("  win column: the question is whether the distance pays for itself.")
    print()

    # 3. What a cap would have recovered -- as an upper bound, stated so.
    print("NEAR MISSES  (losers by how far they ran first)")
    losers = [r for r in cl if r["exit_reason"] != "target_hit"]
    have_mfe = [r for r in losers if _f(r, "mfe_r") is not None]
    if not have_mfe:
        print("  No MFE recorded; skipping.")
    else:
        print(f"  {len(have_mfe)} losers with MFE recorded, of {len(losers)}")
        for thresh in (1.0, 2.0, 3.0, 5.0):
            reached = [r for r in have_mfe if _f(r, "mfe_r") >= thresh]
            if not reached:
                continue
            # Swapping each loser's actual result for the capped target.
            gain = sum(thresh - _f(r, "r_multiple") for r in reached)
            print(f"    reached {thresh:>3.0f}R before losing: {len(reached):>5} "
                  f"({100.0*len(reached)/len(losers):>4.1f}% of losers)  "
                  f"a {thresh:.0f}R cap recovers up to {gain:>8.1f}R")
        print()
        print("  UPPER BOUND, and the gap is real. MFE does not record WHEN the")
        print("  favourable move happened, so a trade that dipped to its stop")
        print("  first and only then ran is counted here as recoverable when it")
        print("  would in fact have been closed. Treat this as 'is it worth")
        print("  testing a cap', not as the result of testing one.")
    print()

    # 4. The cost of trading this often.
    print("SPREAD SENSITIVITY")
    gross_per = pooled["per"]
    print(f"  gross edge            {gross_per:>6.3f} R/trade over {pooled['n']} trades")
    print(f"  breakeven spread      {gross_per:>6.3f} R/round trip")
    if gross_per <= 0:
        print("  The system is negative BEFORE costs. Spread is not the problem")
        print("  here and reducing the trade count will not fix it on its own.")
    else:
        print(f"  at {args.spread} R assumed:  {pooled['net_total']:>8.1f}R net")
        print("  Cost scales with the NUMBER of trades while edge scales with R,")
        print("  so an overtrading system dies on costs even with a real edge.")
    print()

    # 5. Is this a portfolio result or a pile of simultaneous bets?
    print("CONCURRENCY AT ENTRY")
    conc = [int(float(r["concurrent_open_positions_at_entry"]))
            for r in cl if (r.get("concurrent_open_positions_at_entry") or "").strip()]
    if not conc:
        print("  Not recorded.")
    else:
        conc.sort()
        counts = Counter(conc)
        print(f"  median {conc[len(conc)//2]}   "
              f"p90 {conc[int(len(conc)*0.9)]}   max {conc[-1]}")
        top = ", ".join(f"{k}:{v}" for k, v in sorted(counts.items())[:8])
        print(f"  distribution (open positions : trades opened there)  {top}")
        print()
        print("  These are positions open ON ONE INSTRUMENT at the moment of")
        print("  entry. A high number means the per-trade R is not a portfolio")
        print("  result: at 0.5% risk, ten open positions is 5% of the account")
        print("  live at once on a single pair, before any correlation with the")
        print("  other twenty-six.")


if __name__ == "__main__":
    main()
