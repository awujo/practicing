"""
Cut the chart at each trade and play forward. Nothing may see the future.

Operator, 2026-09-25: "when we do backtesting manually we have a cutter
that cuts out from when we want to start backtesting and we play as we
go and not seeing into the future."

That is the only honest test, and the engine does not work that way. It
loads every candle, computes levels, confirmations, imbalances and
setups across the WHOLE series, and then relies on scattered `known_at`
filters to pretend it did not. Every one of those filters is a place to
get it wrong, and four have been wrong:

  2026-08-28  key levels usable before their fractal confirmed
  2026-09-18  ERL periods read before they closed
  2026-09-24  sponsored_a_move scanning past the trade
  2026-09-25  imbalances visible one candle early, and the entry
              classification reading three candles past the fill

Each was found by reading code and each took a day. This finds them by
CONSTRUCTION instead: truncate the data at the moment of the trade, run
the same engine, and ask whether the trade still exists and still has
the same stop and target.

A trade that vanishes under truncation was never takeable. A trade
whose stop or target MOVES was decided with information that had not
arrived. Either way the fast backtest counted something that could not
have been traded.

WHY THIS SAMPLES

One truncated run costs what a backtest costs, so checking every trade
would cost trades x backtest. It samples instead, spread evenly through
the series rather than clustered, because a look-ahead that only bites
in one year is still a look-ahead. A clean sample is not proof; a dirty
one is proof of a bug.

USAGE

    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.replay_check --instrument EURUSD --sample 12

    # against the live windows the bot actually uses
    ... --instrument EURUSD --sample 12 --windows live
"""

from __future__ import annotations

import argparse
import csv
import os
import time

import pandas as pd

from ..engine import runner as R
from ..engine.timeframes import bar_length, closes_at
from .slk_system import slk_kwargs


def _truncating_loader(real_loader, cutoff):
    """`load_candles`, but every series stops at `cutoff`.

    This is the cutter, and it filters on each candle's CLOSE, not its
    open. The first version of this used `c.time <= cutoff` and was
    wrong in the exact way the tool exists to catch: a Daily bar that
    has opened but not closed would be admitted, and its cached high
    and low are the FINAL ones -- so cutting at 15:00 would hand the
    engine the whole of that day's range, including the afternoon that
    has not happened yet.

    Cutting on the close is what a manual backtester's cutter does. A
    period still forming is simply not on the chart."""
    def load(source, symbol, granularity):
        candles = real_loader(source, symbol, granularity)
        if not candles:
            return candles
        length = bar_length(candles)
        return [c for c in candles if closes_at(c.time, length) <= cutoff]
    return load


def replay_one(instrument, entry_style, cutoff, kwargs):
    """Run the engine as it would have run at `cutoff`, and return the
    trades it would have had open or just taken."""
    real = R.load_candles
    R.load_candles = _truncating_loader(real, cutoff)
    try:
        return R.run_backtest(instrument, entry_style, **kwargs)
    finally:
        R.load_candles = real


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--instrument", required=True)
    p.add_argument("--entry-style", default="conservative")
    p.add_argument("--sample", type=int, default=10,
                   help="how many trades to re-derive under truncation")
    p.add_argument("--windows", default="full", choices=("full", "live"))
    p.add_argument("--results-dir", default="backtest/results")
    p.add_argument("--suffix", default="_slk")
    args = p.parse_args()

    kwargs = slk_kwargs()
    if args.windows == "live":
        from .live_cycle_timing import load_windows
        kwargs["max_history_years"] = load_windows(
            instruments=[args.instrument])(args.instrument)

    path = os.path.join(args.results_dir,
                        f"{args.instrument}_{args.entry_style}{args.suffix}.csv")
    if not os.path.exists(path):
        raise SystemExit(f"no trade log at {path} -- run run_slk first")
    with open(path, newline="") as fh:
        rows = [r for r in csv.DictReader(fh)
                if r.get("exit_reason") in ("target_hit", "stop_hit")]
    if not rows:
        raise SystemExit("no closed trades to check")

    stride = max(1, len(rows) // args.sample)
    picked = rows[::stride][:args.sample]

    print(f"REPLAY CHECK  {args.instrument}  {len(picked)} of {len(rows)} trades")
    print("  Each is re-derived with the series cut at its own entry candle.")
    print()
    print(f"  {'entry':<20} {'verdict':<12} detail")
    print("  " + "-" * 72)

    survived = moved = vanished = 0
    for row in picked:
        entry_t = pd.Timestamp(row["entry_time"])
        # The decision is made on the entry candle's CLOSE, so that is
        # the moment to cut at -- not its open, which would hide the
        # very candle the trigger fired on.
        cutoff = entry_t + pd.Timedelta(hours=1)
        t0 = time.time()
        try:
            recs = replay_one(args.instrument, args.entry_style, cutoff, kwargs)
        except Exception as exc:
            print(f"  {str(entry_t)[:16]:<20} {'ERROR':<12} "
                  f"{type(exc).__name__}: {exc}")
            vanished += 1
            continue
        match = next((t for t in recs if t.entry_time == entry_t), None)
        secs = time.time() - t0

        if match is None:
            vanished += 1
            print(f"  {str(entry_t)[:16]:<20} {'VANISHED':<12} "
                  f"not produced when the future is hidden  [{secs:.0f}s]")
            continue

        drift = []
        for field in ("stop_loss", "primary_target"):
            then = getattr(match, field, None)
            now = float(row[field]) if row.get(field) else None
            if then is not None and now is not None and abs(then - now) > 1e-9:
                drift.append(f"{field} {now:.5f} -> {then:.5f}")
        if drift:
            moved += 1
            print(f"  {str(entry_t)[:16]:<20} {'MOVED':<12} "
                  f"{'; '.join(drift)}  [{secs:.0f}s]")
        else:
            survived += 1
            print(f"  {str(entry_t)[:16]:<20} {'ok':<12} "
                  f"same stop and target  [{secs:.0f}s]")

    n = len(picked)
    print()
    print("=" * 76)
    print(f"  survived {survived}/{n}    moved {moved}    vanished {vanished}")
    print()
    if vanished or moved:
        print("  A VANISHED trade was never takeable: the engine only produces it")
        print("  once candles after the entry exist. A MOVED one was takeable but")
        print("  its stop or target was decided with information that had not")
        print("  arrived. Both mean the fast backtest counted something nobody")
        print("  could have traded, and every figure built on it is overstated.")
    else:
        print("  Every sampled trade reproduces identically with the future")
        print("  hidden. That is not proof of no look-ahead anywhere -- it is a")
        print("  sample -- but it is the evidence that was missing.")


if __name__ == "__main__":
    main()
