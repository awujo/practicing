"""
Read the trade-log CSVs a previous backtest already wrote and summarise
them. Runs in seconds, because it re-runs nothing.

Every other tool in here calls `run_backtest()` again, which on full
history is hours. When the question is "what did the run we already did
actually say?", that is the wrong tool: the answer is sitting in
backtest/results/*.csv, one row per trade, written by
`trade_log.write_trade_log()`.

Usage (VPS):

    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.summarize_results

    # one pair, or one variant
    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.summarize_results --match EURUSD
    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.summarize_results --match _erltarget

Filenames carry the flags: `{instrument}_{style}{suffix}.csv`, where the
suffix records year, rr, and any non-default mode (`_noerlcap`,
`_erltarget`, `_wickbreakout`, `_irl*`). A file with no suffix is a
default-flag run. `--match` is a plain substring against the filename,
so it selects either a pair or a variant.

--qmr additionally breaks the trades down by `qmr_test_count`, which is
the measurement item 7 of knowledge-base/STRATEGY_VS_IMPLEMENTATION.md
asks for. 4th man (video 17) teaches that a key level tested and
respected 2+ times before it was finally disrespected is the one price
returns to, quoted at ~80%. The engine records that count on every trade
and then ignores it -- `ranking.py` is deliberately disconnected in
favour of Bishop's react-in-order reading. This says whether ignoring it
costs anything, using trades that already exist.

Treat a difference across QMR buckets as a correlation and nothing more.
The buckets are not randomised, they are whatever the strategy happened
to take, so a gap is a reason to run the A/B, not a result on its own.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
from collections import defaultdict

RESULTS_DIR = "backtest/results"
CLOSED = ("closed_win", "closed_loss", "closed_breakeven")


def load(path):
    """Closed trades with a usable R. Open trades are excluded rather
    than counted as zero -- they have no outcome yet, and folding them in
    at 0R silently dilutes every average."""
    out = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("status") not in CLOSED:
                continue
            try:
                row["_r"] = float(row["r_multiple"])
            except (TypeError, ValueError):
                continue
            out.append(row)
    return out


def stats(rows):
    n = len(rows)
    if not n:
        return None
    wins = [r for r in rows if r["status"] == "closed_win"]
    total = sum(r["_r"] for r in rows)
    capped = sum(1 for r in rows if str(r.get("erl_capped", "")).lower() in ("true", "1"))
    return {
        "n": n,
        "win": 100.0 * len(wins) / n,
        "total": total,
        "per": total / n,
        "avg_win": (sum(r["_r"] for r in wins) / len(wins)) if wins else 0.0,
        "capped": capped,
    }


def row(label, s, width=34):
    return (f"{label:<{width}} {s['n']:>6} {s['win']:>6.1f}% {s['total']:>9.1f}R "
            f"{s['per']:>7.3f} {s['avg_win']:>7.2f} {s['capped']:>6}")


def header(width=34):
    return (f"{'file':<{width}} {'trades':>6} {'win':>7} {'total':>10} "
            f"{'R/trd':>7} {'avgWin':>7} {'capped':>6}")


def qmr_breakdown(rows):
    """Bucketed by prior-test count. 0-1 is "broken on first test", 2+ is
    what 4th man calls the level worth waiting for."""
    buckets = defaultdict(list)
    for r in rows:
        try:
            c = int(float(r.get("qmr_test_count") or 0))
        except (TypeError, ValueError):
            c = 0
        buckets["2+ tests" if c >= 2 else f"{c} test" + ("" if c == 1 else "s")].append(r)
    return buckets


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=RESULTS_DIR)
    ap.add_argument("--match", default="",
                    help="substring against the filename -- a pair (EURUSD) or a "
                         "variant suffix (_erltarget)")
    ap.add_argument("--qmr", action="store_true",
                    help="also break the pooled trades down by qmr_test_count")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.dir, "*.csv")))
    if args.match:
        paths = [p for p in paths if args.match in os.path.basename(p)]
    if not paths:
        where = os.path.abspath(args.dir)
        print(f"no CSVs in {where}" + (f" matching {args.match!r}" if args.match else ""))
        print("Nothing has been run yet, or the run wrote somewhere else "
              "(runner.py's --out overrides the default path).")
        return

    width = max(34, max(len(os.path.basename(p)) for p in paths) + 1)
    print(header(width))
    print("-" * (width + 46))

    pooled = []
    for p in paths:
        rows = load(p)
        pooled.extend(rows)
        s = stats(rows)
        name = os.path.basename(p)
        if s is None:
            print(f"{name:<{width}} {'(no closed trades)':>6}")
            continue
        print(row(name, s, width))

    ps = stats(pooled)
    if ps and len(paths) > 1:
        print("-" * (width + 46))
        print(row("POOLED", ps, width))

    if not ps:
        return

    if args.qmr:
        print()
        print("=" * (width + 46))
        print("BY QMR TEST COUNT -- prior tests the key level survived before")
        print("it was disrespected. 4th man (video 17) prefers 2+; the engine")
        print("records this and does not use it.")
        print()
        print(header(width).replace("file", "bucket", 1))
        print("-" * (width + 46))
        buckets = qmr_breakdown(pooled)
        for label in sorted(buckets, key=lambda k: (k != "2+ tests", k)):
            bs = stats(buckets[label])
            if bs:
                print(row(label, bs, width))
        print()
        print("  Not randomised -- these are the trades the strategy happened to")
        print("  take. A gap here is a reason to run the A/B, not a result.")


if __name__ == "__main__":
    main()
