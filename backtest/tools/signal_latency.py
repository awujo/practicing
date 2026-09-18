"""
When a signal appears, how long AFTER its own candle does it become
visible to run_backtest()?

The question this answers (2026-09-18). The live audit database shows
signals being discovered absurdly late -- CHFJPY's 2026-09-09 14:00
signal was first acted on at 2026-09-16 22:09, seven days and six hours
after the candle that produced it. Both bots then decline it as stale,
correctly, and no trade is ever placed. Two explanations fit:

  (a) The bot did not LOOK. The hourly loop skipped the instrument --
      storyline gate, cycle overrun, reconnect gap -- and only ran
      run_backtest() days later, at which point the backlog came out
      all at once, every item already dead.

  (b) The signal did not EXIST yet. run_backtest() replays all history
      every time, and a setup's existence can depend on candles that
      postdate it: `detect_confirmations` needs candles after a pivot to
      confirm it, key levels re-rank as new highs and lows form, and the
      bias cascade's origin can shift. If a signal at time T only becomes
      computable at T+7d, then NO polling frequency can ever catch it in
      time, and every fix aimed at the decline path is beside the point.

These have opposite remedies, and guessing between them has already cost
days. So measure: truncate the cached candles to what actually existed
at T+k, run the real run_backtest(), and ask whether the signal at T is
in the output. The smallest k where it appears is the signal's latency.

  latency ~1h   -> it existed immediately; the bot simply never looked.
                   Fix the loop, not the engine.
  latency days  -> the engine invents it after the fact. The strategy as
                   implemented cannot be traded live at all in its
                   current form, and that is the finding.

Truncation models the live cache honestly: a bar is kept only if it had
fully CLOSED by the as-of time. Keeping the partially-formed Daily bar
that contains the as-of instant would hand the replay information the
live bot provably does not have (that is the same incomplete-bar bug
fixed in live_cache_sync.py on 2026-09-17).

Needs real cached data (the VPS); this checkout has none.

Usage:

    docker exec -u abc -w /config/trading mt5 nice -n 19 python3 \\
        -m backtest.tools.signal_latency \\
        --targets CHFJPY@2026-09-09T14:00,AUDUSD@2026-09-11T10:00
"""

from __future__ import annotations

import argparse
import sys
import time
from unittest import mock

import pandas as pd

from ..engine import runner as runner_module
from ..engine.candles import load_candles as real_load_candles
from ..engine.runner import run_backtest
from .live_flags import LIVE_LAUNCH_FLAGS, LIVE_FIXED_FLAGS

# How long each granularity's bar lasts, for deciding whether it had
# closed by the as-of time. Anything not listed passes through on the
# bar's own timestamp alone.
BAR_LENGTH = {
    "W": pd.Timedelta(days=7),
    "D": pd.Timedelta(days=1),
    "H4": pd.Timedelta(hours=4),
    "H1": pd.Timedelta(hours=1),
}

DEFAULT_OFFSETS = "1,3,6,12,24,48,96,168,336"


def truncating_loader(as_of):
    """A stand-in for candles.load_candles() serving only the bars that
    had fully closed at `as_of`.

    Closed, not merely started: a Daily bar stamped 09-09 00:00 does not
    exist as a usable candle at 09-09 15:00, and including it would let
    the replay see a whole day's range hours before the day ended. The
    live cache does not contain it (live_cache_sync drops trailing
    incomplete bars), so neither may this."""
    def _load(source: str, symbol: str, granularity: str):
        candles = real_load_candles(source, symbol, granularity)
        length = BAR_LENGTH.get(granularity)
        if length is None:
            return [c for c in candles if c.time <= as_of]
        return [c for c in candles if c.time + length <= as_of]
    return _load


def _live_kwargs(args):
    """Exactly the flags orchestrator._check_instrument() passes. A
    latency measured under different flags is a latency for a strategy
    the bot is not running."""
    return dict(source=args.source, **LIVE_FIXED_FLAGS,
                stop_anchor=args.stop_anchor,
                origin_kind=args.origin_kind,
                close_based_sweep_break=args.close_based_sweep_break)


def visible_at(instrument, entry_style, as_of, args):
    """The set of signal entry times run_backtest() would have reported
    if it had been run at `as_of`."""
    with mock.patch.object(runner_module, "load_candles", truncating_loader(as_of)):
        records = run_backtest(instrument, entry_style, **_live_kwargs(args))
    return {pd.Timestamp(r.entry_time) for r in records}


def parse_targets(raw):
    out = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "@" not in item:
            raise SystemExit(f"bad target {item!r} -- want INSTRUMENT@2026-09-09T14:00")
        instrument, when = item.split("@", 1)
        out.append((instrument.strip().upper(), pd.Timestamp(when, tz="UTC")))
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--targets", required=True,
                    help="comma-separated INSTRUMENT@ISO entry times, e.g. "
                         "CHFJPY@2026-09-09T14:00,AUDUSD@2026-09-11T10:00")
    ap.add_argument("--offsets", default=DEFAULT_OFFSETS,
                    help="hours after the signal candle to test, ascending "
                         f"(default {DEFAULT_OFFSETS})")
    ap.add_argument("--entry-style", default="conservative",
                    choices=("aggressive", "conservative"))
    ap.add_argument("--source", default="dukascopy")
    # Defaults come from the deployed launch command, not LiveBot's
    # dataclass -- see live_flags.py for why that distinction cost a run.
    ap.add_argument("--stop-anchor", default=LIVE_LAUNCH_FLAGS["stop_anchor"])
    ap.add_argument("--origin-kind", default=LIVE_LAUNCH_FLAGS["origin_kind"],
                    choices=("sweep_break", "any"))
    ap.add_argument("--wick-based-sweep-break", dest="close_based_sweep_break",
                    action="store_false",
                    default=LIVE_LAUNCH_FLAGS["close_based_sweep_break"],
                    help="turn OFF --close-based-sweep-break, which the live bots "
                         "are launched WITH and which is therefore the default here")
    args = ap.parse_args()

    sys.stdout.reconfigure(line_buffering=True)
    offsets = [int(x) for x in args.offsets.split(",") if x.strip()]
    targets = parse_targets(args.targets)

    print(f"style={args.entry_style}  offsets(h)={offsets}")
    print(f"flags: origin_kind={args.origin_kind}  "
          f"close_based_sweep_break={args.close_based_sweep_break}  "
          f"stop_anchor={args.stop_anchor}")
    print("a bar counts as available only once it has fully closed")
    print()

    results = []
    for instrument, entry_time in targets:
        print(f"{instrument} @ {entry_time}")

        # Full, untruncated history first. If the signal is not even in
        # today's output there is nothing to time, and the target came
        # from somewhere stale -- say so rather than reporting "never
        # appeared", which would read as a much stronger claim.
        t0 = time.time()
        today = visible_at(instrument, args.entry_style,
                           pd.Timestamp.now(tz="UTC"), args)
        print(f"    full history now: {len(today)} signals total, "
              f"target present: {entry_time in today}  [{time.time() - t0:.0f}s]")
        if entry_time not in today:
            print("    -> cannot measure latency for a signal today's run "
                  "does not produce")
            results.append((instrument, entry_time, None, "not in today's run"))
            print()
            continue

        found = None
        for hours in offsets:
            as_of = entry_time + pd.Timedelta(hours=hours)
            t0 = time.time()
            seen = visible_at(instrument, args.entry_style, as_of, args)
            hit = entry_time in seen
            print(f"    +{hours:>4}h (as of {as_of:%a %d %b %H:%M})  "
                  f"{len(seen):>4} signals  target: {'YES' if hit else 'no':<3} "
                  f"[{time.time() - t0:.0f}s]")
            if hit:
                found = hours
                break

        if found is None:
            note = f"not visible within +{offsets[-1]}h"
        else:
            note = f"first visible at +{found}h"
        results.append((instrument, entry_time, found, note))
        print(f"    -> {note}")
        print()

    print("=" * 70)
    print("LATENCY SUMMARY")
    for instrument, entry_time, found, note in results:
        print(f"  {instrument:<9} {str(entry_time):<26} {note}")
    print()
    measured = [f for _, _, f, _ in results if f is not None]
    if not measured:
        print("  Nothing measurable -- no conclusion.")
    elif max(measured) <= 3:
        print("  Signals exist within hours of their own candle.")
        print("  The engine is not the problem: the bot did not look in time.")
        print("  Next: why the hourly loop skipped these instruments")
        print("  (storyline gate, cycle overrun, reconnect gaps).")
    else:
        print("  Signals take many hours to become computable.")
        print("  No polling frequency can catch these in time -- the entry")
        print("  detection depends on candles that postdate the entry.")
        print("  Next: find which stage moves (confirmations, key levels,")
        print("  bias origin) and whether it is legitimate or a look-ahead.")


if __name__ == "__main__":
    main()
