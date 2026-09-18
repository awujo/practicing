"""
Does the strategy produce ANY signals right now?

Written 2026-09-18, after two weeks with no live trade and two days
spent fixing things that turned out not to be the problem. Every
decline-path fix (stale cutoff, drift guard, limit reroute, wrong-account
guard) addressed entry ATTEMPTS -- and the audit database showed zero
attempts for the last 26 hours, and only 31 in the two weeks before.
A decline cannot be the cause of silence when nothing is being declined.

So: stop fixing the plumbing and measure the source. This prints, per
instrument, how many trades `run_backtest()` produces in a window --
called exactly the way `orchestrator._check_instrument()` calls it, same
flags, same defaults -- plus the funnel above it so a zero is
diagnosable rather than just disappointing:

    breakouts -> setups -> H1 candidates -> recorded trades

If the funnel dies at "breakouts", bias/structure is the problem. If it
dies at "setups", liquidity or key levels. If it dies at "candidates",
the sweep/reaction scan. If trades come out but the bot took none, the
strategy is fine and the LIVE path is broken -- a completely different
investigation, and the point of running this.

Deliberately not included: the storyline gate (`live_strategy`). That is
a live-only filter and replaying it per H1 candle costs roughly a Daily
+ H4 pass each. It only matters once this number is non-zero.

An earlier one-liner doing this died silently partway with no output at
all, which is why this prints and flushes after EVERY instrument and
reports elapsed time and peak RSS per instrument: a run that gets killed
still leaves behind everything it had already computed, and the memory
column says whether it was killed for growing.

Usage (VPS -- real cached data required, this checkout has none):

    docker exec -u abc -w /config/trading mt5 nice -n 19 python3 \\
        -m backtest.tools.count_signals \\
        --instruments EURUSD,GBPUSD,USDCHF --from 2026-09-04 --to 2026-09-18

Split --instruments across two runs if it gets killed; each instrument
is independent and the totals line just adds up.
"""

from __future__ import annotations

import argparse
import gc
import resource
import sys
import time
import traceback

import pandas as pd

from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..engine.bias import detect_confirmations
from ..engine.candles import load_candles
from ..engine.key_levels import detect_key_levels
from ..engine.runner import (
    run_backtest, _find_liquidity_setups, _find_entry_candidates,
    _trim_to_recent_years,
)
from .live_flags import LIVE_LAUNCH_FLAGS, LIVE_FIXED_FLAGS


def _rss_mb():
    # ru_maxrss is the high-water mark for the whole process, so this is
    # cumulative across instruments by design -- a flat column means the
    # run is not leaking, a climbing one names the instrument that would
    # get it OOM-killed.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _when(t):
    return pd.Timestamp(t).strftime("%a %d %b %H:%M") if t is not None else "-"


def funnel(instrument, source, start, end, n, years):
    """The three stages above run_backtest, counted inside the window.

    Cheap relative to the backtest itself (no trade loop, no bias
    cascade) and it is what turns "0 trades" into a location."""
    h4 = load_candles(source, instrument, "H4")
    h1 = load_candles(source, instrument, "H1")
    h4 = _trim_to_recent_years(h4, years)
    h1 = _trim_to_recent_years(h1, years)
    if not h4:
        return None

    confs = sorted(detect_confirmations(h4, n), key=lambda c: c.time)
    levels = detect_key_levels(h4, n)
    # Explicitly "swing": _find_liquidity_setups defaults to
    # single_candle, run_backtest defaults to swing, and swing is what
    # the live bot runs. Taking the function default here would count a
    # funnel the backtest column below never used.
    setups = _find_liquidity_setups(h4, confs, levels, n, liquidity_mode="swing")
    candidates = _find_entry_candidates(h1, setups)

    in_win = lambda t: start <= pd.Timestamp(t) <= end
    return {
        "breakouts": sum(1 for c in confs if in_win(c.time)),
        "setups": sum(1 for s in setups if in_win(s.liquidity_time)),
        "candidates": sum(1 for c in candidates
                          if c.index < len(h1) and in_win(h1[c.index].time)),
        "last_breakout": confs[-1].time if confs else None,
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instruments", required=True, help="comma-separated, or ALL")
    ap.add_argument("--source", default="dukascopy")
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--entry-style", default="conservative",
                    choices=("aggressive", "conservative"))
    # These must match the DEPLOYED launch command, not LiveBot's
    # dataclass defaults. Both bots are started with `--origin-kind any
    # --close-based-sweep-break`, which overrides those defaults, so
    # pinning to the dataclass measured a strategy nobody is running
    # (verified from ps on the VPS, 2026-09-18 -- the first version of
    # this tool got it wrong and a test asserting it matched LiveBot
    # passed anyway, because the mismatch is at the launch site).
    ap.add_argument("--stop-anchor", default=LIVE_LAUNCH_FLAGS["stop_anchor"])
    ap.add_argument("--origin-kind", default=LIVE_LAUNCH_FLAGS["origin_kind"],
                    choices=("sweep_break", "any"))
    ap.add_argument("--wick-based-sweep-break", dest="close_based_sweep_break",
                    action="store_false",
                    default=LIVE_LAUNCH_FLAGS["close_based_sweep_break"],
                    help="turn OFF --close-based-sweep-break, which the live bots "
                         "are launched WITH and which is therefore the default here")
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--funnel-years", type=float, default=1.0,
                    help="trailing history for the funnel counts only; the backtest "
                         "itself always runs on full history like the live bot")
    ap.add_argument("--no-funnel", action="store_true",
                    help="skip the breakout/setup/candidate counts and only run the "
                         "backtest -- roughly halves the work per instrument")
    args = ap.parse_args()

    sys.stdout.reconfigure(line_buffering=True)
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(days=1)

    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]

    print(f"window {start.date()} .. {(end - pd.Timedelta(days=1)).date()}   "
          f"style={args.entry_style}")
    # Printed, not assumed: a count is only checkable if the flags that
    # produced it are visible next to it. See live_flags.py.
    print("flags (must match the deployed launch command):")
    print("  " + "  ".join(f"{k}={v}" for k, v in LIVE_FIXED_FLAGS.items())
          + f"  stop_anchor={args.stop_anchor}  origin_kind={args.origin_kind}"
          + f"  close_based_sweep_break={args.close_based_sweep_break}")
    print()
    print(f"{'instrument':<10} {'brk':>4} {'setup':>6} {'cand':>5} {'TRADES':>7} "
          f"{'all-time':>9} {'secs':>6} {'rssMB':>7}  last signal")
    print("-" * 92)

    total_window = 0
    total_all = 0
    ran = 0
    hits = []

    for instrument in instruments:
        t0 = time.time()
        try:
            f = None if args.no_funnel else funnel(
                instrument, args.source, start, end, args.n, args.funnel_years)
            records = run_backtest(
                instrument, args.entry_style, source=args.source,
                **LIVE_FIXED_FLAGS,
                stop_anchor=args.stop_anchor,
                origin_kind=args.origin_kind,
                close_based_sweep_break=args.close_based_sweep_break,
            )
        except FileNotFoundError:
            print(f"{instrument:<10} no cached data")
            continue
        except Exception:
            print(f"{instrument:<10} FAILED after {time.time() - t0:.0f}s:")
            traceback.print_exc()
            continue

        in_window = [r for r in records
                     if start <= pd.Timestamp(r.entry_time) <= end]
        last = max((pd.Timestamp(r.entry_time) for r in records), default=None)
        ran += 1
        total_window += len(in_window)
        total_all += len(records)
        hits.extend((instrument, r) for r in in_window)

        cols = ("   -     -     -" if f is None
                else f"{f['breakouts']:>4} {f['setups']:>6} {f['candidates']:>5}")
        print(f"{instrument:<10} {cols} {len(in_window):>7} {len(records):>9} "
              f"{time.time() - t0:>6.0f} {_rss_mb():>7.0f}  {_when(last)}")

        # Full history per instrument is hundreds of MB of Candle objects;
        # without this the run grows until it is killed, which is the
        # most likely reason the first attempt at this produced no output.
        del records, in_window
        gc.collect()

    print("-" * 92)
    print(f"{'TOTAL':<10} {'':>17} {total_window:>7} {total_all:>9}")
    print()

    if not ran:
        # Without this the "ZERO signals" verdict below would fire on a
        # run where nothing was measured at all -- a wrong answer to the
        # one question this tool exists to answer.
        print("No instrument actually ran (no cached data, or all failed).")
        print("Nothing was measured -- this is not a zero-signal result.")
        return

    if not hits:
        print("ZERO signals in the window.")
        print("The live path is not the problem -- there was nothing to execute.")
        print("Read the funnel columns above for where it stops:")
        print("  brk=0    -> no confirmed H4 breakouts: bias/structure")
        print("  setup=0  -> breakouts but no liquidity+key level pairing")
        print("  cand=0   -> setups but no sweep-and-react on H1")
        print("  cand>0, TRADES=0 -> a downstream gate (alignment, IRL/ERL,")
        print("                      rollover, zone fill, R:R, min_reward_r)")
        return

    print(f"{len(hits)} signals in the window. Every one of these is something")
    print("the bot should have attempted -- cross-check against the audit")
    print("database's entry_attempt rows for the same times.")
    print()
    print(f"  {'instrument':<10} {'entry time':<21} {'side':<9} {'trigger':<12} outcome")
    for instrument, r in sorted(hits, key=lambda x: str(x[1].entry_time)):
        side = str(getattr(r.direction, "value", r.direction))
        print(f"  {instrument:<10} {str(r.entry_time):<21} {side:<9} "
              f"{r.trigger_type:<12} {r.exit_reason or 'still_open'}")


if __name__ == "__main__":
    main()
