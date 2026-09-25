"""
Read the per-trade CSVs and ask which trades were actually SLK.

    docker exec -u abc -w /config/trading mt5 python3 -m backtest.slk.analyse \\
        --dir backtest/results/slk

WHY THIS EXISTS

The first full-history run said the engulf entry has no edge at all --
1,322 trades on AUDCAD, gross profit factor 0.99, dead flat before costs.
That is either the strategy or the implementation, and the way to tell
them apart is to ask how far the entries sat from the key level they were
supposed to be playing.

On a synthetic run the answer was: median 1.3R away, 58% beyond 1R, 15%
beyond 3R, one at 19R. And the distance tracked the result --

    sweep_break   median 1.0R from the level     +0.91 R/trade
    engulf        median 1.2R, tail to 19R       -0.18 R/trade
    breakout      median 2.0R                    -0.51 R/trade

-- which is what you would expect if the far ones are not really trading
that level at all. "Eventually you want to see price come into your K
level and boom, you buy" (repeating-system t=354-360) does not describe
an entry three risk-units away from it.

THE TEST, AND WHY IT IS NOT A THRESHOLD

No pip distance and no R cutoff is invented here. The question asked is
structural and comes from SLK_SPEC 6: "the stop sits where the setup is
INVALIDATED, which is beyond the structure that defines it." The
structure defining the setup is the key level. So either the trade's risk
reaches back past that level -- price going through it takes you out, and
you were genuinely trading it -- or it does not, and the level was a flag
that said "you may trade" rather than the thing being traded.

That is a yes/no question about each trade, answerable from the CSV, with
no number chosen by me. This tool only REPORTS the split. Whether it
becomes a rule depends on what the numbers say, on real data, which is
the whole point of measuring first.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
from collections import defaultdict

from ..engine.runner import default_pip_size


def _rows(directory: str):
    for path in sorted(glob.glob(os.path.join(directory, "*.csv"))):
        instrument = os.path.basename(path).split("_")[0]
        with open(path) as handle:
            for row in csv.DictReader(handle):
                if row.get("outcome") not in ("target", "stop"):
                    continue
                try:
                    row["_r"] = float(row["r"])
                    row["_entry"] = float(row["entry"])
                    row["_stop"] = float(row["stop"])
                    row["_setup"] = float(row["setup_price"])
                except (TypeError, ValueError):
                    continue          # a column that never got written
                row["_instrument"] = instrument
                row["_risk"] = abs(row["_entry"] - row["_stop"])
                yield row


def covers_level(row) -> bool:
    """Does this trade's risk reach back past the key level?

    For a buy the stop sits below the entry; the level is covered when the
    stop is at or below it, so price going through the level takes the
    trade out. Mirrored for a sell.
    """
    if not row["_risk"]:
        return False
    if row["direction"] == "bullish":
        return row["_stop"] <= row["_setup"]
    return row["_stop"] >= row["_setup"]


def distance_r(row) -> float:
    """How far the entry sat from the key level, in this trade's own risk."""
    return abs(row["_entry"] - row["_setup"]) / row["_risk"] if row["_risk"] else 0.0


def _stats(rows):
    n = len(rows)
    if not n:
        return None
    wins = [r for r in rows if r["outcome"] == "target"]
    total = sum(r["_r"] for r in rows)
    won = sum(r["_r"] for r in wins)
    lost = -sum(r["_r"] for r in rows if r["outcome"] != "target")
    return {"n": n, "win": 100.0 * len(wins) / n, "total": total,
            "per": total / n,
            "pf": (won / lost) if lost else float("inf")}


def _line(label, s, width=22):
    if not s:
        return f"  {label:<{width}} no trades"
    return (f"  {label:<{width}} {s['n']:>6}  win {s['win']:>5.1f}%  "
            f"{s['per']:>+6.2f} R/trade  {s['total']:>+9.1f}R  PF {s['pf']:>5.2f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="backtest/results/slk")
    args = parser.parse_args()

    rows = list(_rows(args.dir))
    if not rows:
        raise SystemExit(f"no usable rows under {args.dir}")

    print(f"{len(rows)} closed trades from "
          f"{len({r['_instrument'] for r in rows})} instruments\n")
    print("R figures are GROSS here -- spread is charged in run.py, not in "
          "the CSV.\n")

    print("DOES THE TRADE'S RISK REACH BACK PAST ITS KEY LEVEL?")
    print("  SLK_SPEC 6: the stop belongs beyond the structure that defines")
    print("  the setup, and that structure is the key level.")
    covered = [r for r in rows if covers_level(r)]
    loose = [r for r in rows if not covers_level(r)]
    print(_line("covers the level", _stats(covered)))
    print(_line("does not", _stats(loose)))

    print("\nBY DISTANCE FROM THE KEY LEVEL (in the trade's own risk)")
    buckets = [(0, 0.5), (0.5, 1), (1, 2), (2, 4), (4, float("inf"))]
    grouped = defaultdict(list)
    for row in rows:
        gap = distance_r(row)
        for low, high in buckets:
            if low <= gap < high:
                grouped[(low, high)].append(row)
                break
    for low, high in buckets:
        label = f"{low}-{high}R" if high != float("inf") else f"{low}R+"
        print(_line(label, _stats(grouped[(low, high)])))

    print("\nBY FORM")
    by_form = defaultdict(list)
    for row in rows:
        by_form[row["form"]].append(row)
    for form in sorted(by_form):
        print(_line(form, _stats(by_form[form])))
        inner = [r for r in by_form[form] if covers_level(r)]
        print(_line(f"  {form} covering", _stats(inner)))

    print("\nBY INSTRUMENT")
    by_inst = defaultdict(list)
    for row in rows:
        by_inst[row["_instrument"]].append(row)
    for instrument in sorted(by_inst):
        print(_line(instrument, _stats(by_inst[instrument])))

    print("\nHOW BIG IS THE RISK, IN PIPS?")
    print("  The stop is the confirming candle's far side, UNPADDED. If that")
    print("  distance sits inside ordinary noise on the entry timeframe, the")
    print("  trade dies in the bar it is born and the spread costs a fortune")
    print("  in R -- 1 pip of spread on 6 pips of risk is 0.17R per trade.")
    pips = []
    for r in rows:
        pip = default_pip_size(r["_instrument"])
        pips.append((r["_risk"] / pip, r))
    pips.sort(key=lambda row: row[0])
    for label, low, high in (("under 5 pips", 0, 5), ("5-10 pips", 5, 10),
                             ("10-20 pips", 10, 20), ("20-50 pips", 20, 50),
                             ("50 pips+", 50, float("inf"))):
        bucket = [r for size, r in pips if low <= size < high]
        print(_line(label, _stats(bucket)))
        amb = sum(1 for r in bucket if r.get("same_candle_stop") == "1")
        if bucket:
            print(f"  {'':<22} {100.0 * amb / len(bucket):>5.0f}% of these "
                  f"died in the bar they filled")

    print("\nDOES COVERING THE LEVEL GIVE THE TRADE ROOM TO BREATHE?")
    for label, subset in (("covers the level", covered), ("does not", loose)):
        if not subset:
            continue
        amb = sum(1 for r in subset if r.get("same_candle_stop") == "1")
        median = sorted(r["_risk"] / default_pip_size(r["_instrument"])
                        for r in subset)[len(subset) // 2]
        print(f"  {label:<22} median risk {median:>5.1f} pips, "
              f"{100.0 * amb / len(subset):>4.0f}% died in their own bar")

    ambiguous = [r for r in rows if r.get("same_candle_stop") == "1"]
    if ambiguous:
        print(f"\n{len(ambiguous)} of {len(rows)} fills "
              f"({100.0 * len(ambiguous) / len(rows):.0f}%) were ambiguous -- "
              f"one bar reached both entry and stop, assumed filled then "
              f"stopped.")
        kept = [r for r in rows if r.get("same_candle_stop") != "1"]
        print(_line("without them", _stats(kept)))
        print("  That is the other assumption, not the truth: those trades")
        print("  are real if price traded through the entry. It is here so")
        print("  the size of the assumption is visible.")


if __name__ == "__main__":
    main()
