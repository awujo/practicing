"""
Checks whether the strategy would have produced any entry signal since a
given time, across a set of instruments/styles -- entirely offline,
against the cached candle data (no MT5 connection needed). Built to
answer "did I miss anything during an outage" without needing to run
this against a live account, and without competing for CPU with an
actual live bot process (see bot/README.md's VPS section -- this used
to get run directly on the VPS and slowed the live bots down doing it).

Usage:
    python -m backtest.engine.check_recent_signals --since 2026-08-24T05:00:00
    python -m backtest.engine.check_recent_signals --since 2026-08-24T05:00:00 \
        --instruments EURUSD,GBPUSD --styles conservative
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from .runner import run_backtest
from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS

DEFAULT_EXCLUDE = {"USOIL", "ETHUSD"}  # availability unconfirmed on MetaQuotes-Demo as of writing


def _parse_since(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=_parse_since, default=None,
                         help="ISO datetime (UTC if no offset given). Defaults to 24 hours ago.")
    parser.add_argument("--instruments", default=None,
                         help="Comma-separated internal symbols. Defaults to all instruments except "
                              f"{sorted(DEFAULT_EXCLUDE)}.")
    parser.add_argument("--styles", default="conservative,aggressive",
                         help="Comma-separated entry styles to check.")
    parser.add_argument("--json", dest="json_path", default=None,
                         help="Also write the signals to this path as JSON. This is what the live "
                              "VPS consumes (bot/reconcile_signals.py) to tell whether a signal the "
                              "strategy produced ever reached an audit database -- the VPS can't "
                              "compute these itself without stealing CPU from the running bots.")
    args = parser.parse_args()

    since = args.since or (datetime.now(timezone.utc) - timedelta(hours=24))
    instruments = (args.instruments.split(",") if args.instruments
                   else [s for s in DUKASCOPY_INSTRUMENTS if s not in DEFAULT_EXCLUDE])
    styles = args.styles.split(",")

    now = datetime.now(timezone.utc)
    print(f"Checking for any entry_time >= {since.isoformat()} (now: {now.isoformat()})")
    print(f"{len(instruments)} instruments x {len(styles)} style(s) = {len(instruments) * len(styles)} runs\n")

    found_any = False
    signals = []
    errors = []
    for style in styles:
        for instrument in instruments:
            try:
                # Must match orchestrator.py's _check_instrument() call
                # exactly (avoid_rollover_entries=True, min_reward_r=1.0,
                # both enabled 2026-09-01) -- otherwise this reference
                # feed includes signals the live bots now deliberately
                # skip BEFORE run_backtest() even returns them as
                # candidates, meaning no audit row (not even a decline)
                # is ever logged for them. reconcile_signals.py would
                # then report every one of those as MISSING -- identical
                # in appearance to the real "the bot never saw it" bug
                # this whole feed exists to catch, permanently drowning
                # out genuine misses in predictable, non-actionable noise.
                records = run_backtest(instrument, style,
                                        avoid_rollover_entries=True, min_reward_r=1.0)
            except Exception as exc:
                errors.append((instrument, style, str(exc)))
                continue
            for r in records:
                if r.entry_time >= since:
                    found_any = True
                    signals.append({
                        "instrument": instrument, "style": style,
                        "entry_time": r.entry_time.isoformat(),
                        "direction": getattr(r.direction, "value", str(r.direction)),
                        "entry_price": r.entry_price, "stop_loss": r.stop_loss,
                        "primary_target": r.primary_target,
                        "trigger_type": r.trigger_type, "entry_pattern": r.entry_pattern,
                    })
                    print(f"SIGNAL: {instrument} ({style})  entry_time={r.entry_time}  "
                          f"direction={getattr(r.direction, 'value', r.direction)}  "
                          f"entry_price={r.entry_price}  stop_loss={r.stop_loss}  "
                          f"primary_target={r.primary_target}  status={r.status}"
                          + (f"  exit_reason={r.exit_reason}  r_multiple={r.r_multiple}"
                             if r.status != "still_open" else ""))

    if not found_any:
        print("No signals found in this window on any instrument/style checked.")

    if args.json_path:
        # Written even when empty, and even when some combos errored: a
        # consumer needs to be able to tell "checked, found nothing" from
        # "never ran", and a stale file would silently look like the
        # former. `errored` lets it say which instruments it can't speak
        # for rather than implying they were clean.
        payload = {
            "generated_at": now.isoformat(),
            "since": since.isoformat(),
            "instruments": instruments,
            "styles": styles,
            "signals": sorted(signals, key=lambda s: (s["entry_time"], s["instrument"], s["style"])),
            "errored": [{"instrument": i, "style": st, "error": m} for i, st, m in errors],
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.json_path)), exist_ok=True)
        with open(args.json_path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"\nWrote {len(signals)} signal(s) to {args.json_path}")

    if errors:
        print(f"\n{len(errors)} instrument/style combo(s) errored:", file=sys.stderr)
        for instrument, style, msg in errors:
            print(f"  {instrument} ({style}): {msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
