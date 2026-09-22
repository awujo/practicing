"""
Can this configuration actually fly? Time a live cycle before deploying.

A profitable system that does not fit in the cycle budget is not a
system. The live loop calls the SAME `run_backtest()` the backtest
does, once per instrument per cycle, so anything that makes the
backtest slower makes every live cycle slower too -- and that is not
obvious from the backtest's own runtime, because the backtest runs full
history while live runs a trimmed window.

That trimming is the whole reason the bots keep up today. Most
instruments get 1 year of H1/H4 and 2 of Daily/Weekly
(`bot/history_windows.json`); the full backtest runs ~20 years. So a
backtest taking 15 minutes an instrument says nothing directly about
whether live is fine, and estimating the ratio by hand is exactly the
kind of guess this project has been burned by.

This measures it. Same windows the orchestrator loads, same config, one
timed call per instrument.

WHAT THE NUMBERS MEAN

  cycle total    Seconds to scan every instrument once. The bot works on
                 H1 candles, so the budget is 3600s -- but fitting is
                 not the bar.

  staleness      The real bar. A signal found at the END of a scan has
                 been waiting the whole scan. STALE_ENTRY_CUTOFF is 3h
                 for market orders, so a 40-minute scan spends a fifth
                 of that budget before anyone looks at the signal, and
                 the bot then declines what it cannot reach in time.
                 The two-week no-trade incident of 2026-09 was this
                 failure mode from a different cause, and it was
                 invisible until measured.

USAGE

    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.live_cycle_timing --config slk

    # what the bots run today, for a baseline
    ... --config shipped

    # does capping the pools buy enough to matter
    ... --config slk --max-pools 3

Runs in minutes, not hours, because the windows are small. That is the
point: know whether a configuration is deployable before spending a day
finding out whether it is profitable.
"""

from __future__ import annotations

import argparse
import json
import os
import time

from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..engine.runner import run_backtest
from .slk_system import SLK_OPERATIONAL, slk_kwargs

# The bot's own cycle and staleness numbers, so this reports against
# what actually governs live rather than against a round number.
CYCLE_BUDGET_S = 3600.0          # one H1 candle
STALE_CUTOFF_S = 3 * 3600.0      # bot/orchestrator.py STALE_ENTRY_CUTOFF

WINDOWS_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "bot", "history_windows.json")


def load_windows(path=WINDOWS_PATH, instruments=None):
    """The same file AND the same resolver the live bot uses.

    An earlier version re-implemented the two-tier lookup as
    `per.get(inst, default)`. That happens to agree with the real rule,
    but only by an accident of Python semantics: `dict.get` returns the
    default when a key is ABSENT, not when its value is null -- and an
    explicit null in this file means something specific and load-bearing:

        "an explicit null -- that's 'confirmed NOT safe to cap' (e.g.
         GBPNZD, which never converged even at a 15-year search
         ceiling), deliberately different from 'no data yet'"
                        run_live.resolve_history_window_years

    Agreeing by luck is not agreeing. A timing run against different
    windows than live uses would be measuring a machine nobody runs, so
    this now calls the live resolver and cannot drift from it."""
    from bot.run_live import resolve_history_window_years

    with open(path) as fh:
        data = json.load(fh)
    instruments = tuple(instruments or sorted(DUKASCOPY_INSTRUMENTS))
    resolved = resolve_history_window_years(data, instruments)
    # Uncapped instruments are simply absent, matching run_backtest's
    # own None-means-unbounded convention.
    return lambda inst: resolved.get(inst)


CONFIGS = {
    "shipped": lambda: dict(SLK_OPERATIONAL),
    "slk": slk_kwargs,
}


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="slk", choices=sorted(CONFIGS))
    parser.add_argument("--entry-style", default="conservative",
                        choices=("aggressive", "conservative"))
    parser.add_argument("--instruments", default="ALL")
    parser.add_argument("--max-pools", type=int, default=None,
                        help="cap single-candle liquidity pools per setup. "
                             "Unbounded by default, which is the rule as stated "
                             "but also the most expensive reading of it.")
    args = parser.parse_args()

    kwargs = CONFIGS[args.config]()
    if args.max_pools is not None:
        kwargs["single_candle_max_pools"] = args.max_pools

    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    window_for = load_windows(instruments=instruments)

    print(f"config: {args.config}")
    for k, v in sorted(kwargs.items()):
        print(f"  {k} = {v}")
    print(f"  windows from {os.path.relpath(WINDOWS_PATH)}")
    print(flush=True)

    print(f"{'instrument':<12} {'window (D/W/H4/H1)':<22} {'seconds':>9} {'trades':>7}")
    print("-" * 54, flush=True)

    total = 0.0
    timed = 0
    slowest = ("", 0.0)
    for instrument in instruments:
        window = window_for(instrument)
        t0 = time.time()
        try:
            recs = run_backtest(instrument, args.entry_style,
                                max_history_years=window, **kwargs)
        except FileNotFoundError:
            print(f"{instrument:<12} no cached data, skipped", flush=True)
            continue
        except Exception as exc:
            print(f"{instrument:<12} FAILED: {type(exc).__name__}: {exc}", flush=True)
            continue
        secs = time.time() - t0
        total += secs
        timed += 1
        if secs > slowest[1]:
            slowest = (instrument, secs)
        w = window or {}
        # "uncapped" rather than dashes: GBPNZD's null is a decision, not
        # missing data, and the row should say which.
        label = ("uncapped (full history)" if not w
                 else "/".join(str(w.get(k, "-")) for k in ("D", "W", "H4", "H1")))
        print(f"{instrument:<12} {label:<22} {secs:>9.1f} {len(recs):>7}", flush=True)

    if not timed:
        print("\nNothing timed.")
        return

    print()
    print("=" * 54)
    print(f"instruments timed     {timed}")
    print(f"cycle total           {total:.0f}s  ({total/60:.1f} min)")
    print(f"mean per instrument   {total/timed:.1f}s")
    print(f"slowest               {slowest[0]} at {slowest[1]:.1f}s")
    print()

    # A cycle that fits is necessary, not sufficient. The signal found
    # last has aged by the whole scan before anything looks at it.
    print(f"cycle budget (H1)     {CYCLE_BUDGET_S:.0f}s -- "
          f"using {100*total/CYCLE_BUDGET_S:.0f}%")
    print(f"staleness budget      {STALE_CUTOFF_S:.0f}s (3h market-order cutoff)")
    print(f"  a signal found at the END of a scan is already {total/60:.1f} min old,")
    print(f"  i.e. {100*total/STALE_CUTOFF_S:.0f}% of the cutoff spent before it is looked at.")
    print()

    if total > CYCLE_BUDGET_S:
        print("  DOES NOT FIT. The scan is longer than the candle it reacts to,")
        print("  so the bot falls further behind every cycle. Not deployable.")
    elif total > 0.25 * STALE_CUTOFF_S:
        print("  FITS, BUT THIN. More than a quarter of the staleness budget goes")
        print("  on the scan itself, before execution, slippage or a retry. Worth")
        print("  capping --max-pools and re-timing before trusting it live.")
    else:
        print("  Comfortable. The scan is a small fraction of both budgets.")

    print()
    print("  Measured on THIS machine with whatever else was running. Re-time")
    print("  with the live bots up if that is how it will actually run.")


if __name__ == "__main__":
    main()
