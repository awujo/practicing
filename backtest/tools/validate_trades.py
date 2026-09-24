"""
Is each recorded trade actually an SLK trade? Checked, not eyeballed.

Operator, 2026-09-24: "can you take the backtesting figure and run it
on your engine and visualise if what it is doing is what SLK does."

A rendered chart answers that for ONE trade. This answers it for every
trade in the log, which is the only way to find out whether the losses
are the strategy being wrong or the engine not trading the strategy.

THE TWO CHECKS THAT MATTER, AND WHY

  distance to the level    SLK is a reaction off a key level. Price
                           comes INTO the level, reacts, confirms, and
                           you enter there. So the entry should sit
                           close to the level -- measured in units of
                           the trade's own risk, because that is the
                           scale the trade itself defines. An entry 3R
                           away from its key level is not a reaction
                           off that level; it is a trade that happens
                           to have a level somewhere behind it.

  stop beyond the level    The level is the invalidation. Bishop's
                           stop sits where the SETUP is wrong, and for
                           a reaction off a level that means beyond
                           the level. A bullish stop ABOVE the key
                           level protects nothing: price can trade all
                           the way back through the level, the setup is
                           dead, and the position is still open.

Both are computed from columns the engine already records, so this
needs no re-run and cannot disagree with what was traded.

WHAT A BAD RESULT LOOKS LIKE

If most entries are far from their level and most stops sit on the
wrong side of it, then the engine is not trading SLK and no amount of
tuning targets or triggers will fix the win rate. That is a different
diagnosis from "the strategy does not work", and it is the one this
tool exists to separate.

USAGE

    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.validate_trades --suffix _slk
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
from collections import Counter


def _f(row, key):
    v = (row.get(key) or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load(results_dir, suffix, instruments=None):
    rows = []
    for path in sorted(glob.glob(os.path.join(results_dir, f"*{suffix}.csv"))):
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                if instruments and row.get("instrument") not in instruments:
                    continue
                if row.get("exit_reason") in ("target_hit", "stop_hit"):
                    rows.append(row)
    return rows


def audit(row):
    """(distance_to_level_in_R, stop_protects_level) or None."""
    entry = _f(row, "entry_price")
    stop = _f(row, "stop_loss")
    level = _f(row, "key_level_price")
    if None in (entry, stop, level):
        return None
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    bullish = "bull" in (row.get("direction") or "").lower()
    # Beyond the level, from the entry's side: a bullish trade reacts
    # off support, so its stop belongs BELOW the level.
    protects = stop < level if bullish else stop > level
    return abs(entry - level) / risk, protects


def pct(n, d):
    return f"{100.0 * n / d:>5.1f}%" if d else "    -"


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results-dir", default="backtest/results")
    p.add_argument("--suffix", default="_slk")
    p.add_argument("--instruments", default="")
    args = p.parse_args()

    only = {s.strip().upper() for s in args.instruments.split(",") if s.strip()}
    rows = load(args.results_dir, args.suffix, only or None)
    if not rows:
        print(f"No closed trades in *{args.suffix}.csv")
        return

    seen = [(r, audit(r)) for r in rows]
    usable = [(r, a) for r, a in seen if a]
    n = len(usable)
    print(f"VALIDATE  {n} closed trades with usable geometry "
          f"(of {len(rows)})\n")

    dists = sorted(a[0] for _, a in usable)
    print("HOW FAR FROM ITS KEY LEVEL DID EACH TRADE ENTER?")
    print("  (in units of the trade's own risk -- 1.0 means the entry is")
    print("   as far from the level as the stop is from the entry)")
    print(f"    median {dists[len(dists)//2]:.2f}R   "
          f"p75 {dists[int(len(dists)*.75)]:.2f}R   "
          f"p90 {dists[int(len(dists)*.9)]:.2f}R   max {dists[-1]:.1f}R")
    for lim in (0.25, 0.5, 1.0, 2.0):
        k = sum(1 for d in dists if d <= lim)
        print(f"    within {lim:>4.2f}R of the level: {k:>5} ({pct(k, n)})")
    print()
    print("  SLK enters ON the reaction off the level. A trade whose entry")
    print("  sits further from its level than its own stop distance is not")
    print("  reacting off that level.")
    print()

    good = sum(1 for _, a in usable if a[1])
    print("DOES THE STOP SIT BEYOND THE KEY LEVEL?")
    print(f"    yes  {good:>5} ({pct(good, n)})    no  {n-good:>5} "
          f"({pct(n - good, n)})")
    print()
    print("  The level is the invalidation. A bullish stop ABOVE its key")
    print("  level protects nothing -- price can trade back through the")
    print("  level, the setup is dead, and the position is still open.")
    print()

    # Both conditions at once, by trigger: which code path produces
    # trades that look like the taught setup, and which does not.
    print("BY TRIGGER: share meeting BOTH (entry within 1R, stop beyond level)")
    per = {}
    for r, a in usable:
        t = r.get("trigger_type") or "(none)"
        ok = a[0] <= 1.0 and a[1]
        hit, tot = per.get(t, (0, 0))
        per[t] = (hit + (1 if ok else 0), tot + 1)
    for t, (hit, tot) in sorted(per.items(), key=lambda kv: -kv[1][1]):
        print(f"    {t:<16} {hit:>5} / {tot:<5} {pct(hit, tot)}")
    print()

    both = sum(1 for _, a in usable if a[0] <= 1.0 and a[1])
    print("=" * 66)
    print(f"  {both} of {n} trades ({pct(both, n)}) are recognisably the taught")
    print("  setup: entered within 1R of their key level, with the stop")
    print("  beyond it.")
    print()
    print("  If that share is low, the losses are not the strategy being")
    print("  wrong -- they are the engine not trading the strategy, and no")
    print("  amount of tuning targets or triggers will fix the win rate.")

    shapes = Counter(r.get("key_level_shape") or "?" for r, _ in usable)
    print()
    print("  key level shapes traded: " +
          ", ".join(f"{k}={v}" for k, v in shapes.most_common()))


if __name__ == "__main__":
    main()
