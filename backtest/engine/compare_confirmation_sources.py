"""
A/B test: the current "breakout" definition (detect_confirmations()'s
fractal swing-high/low, aimed at the prior MAJOR extreme) vs. an
alternate "most recent breakout" definition (detect_confirmations_
recent_key_level(), reacting to the nearest A/V-shape key level
instead) -- direct 2026-08-28 user request, following a live JP225
Daily disagreement (see OPEN_QUESTIONS.md for the full context and why
this wasn't just changed outright: STRATEGY.md/Video 17, as sourced in
bias.py, currently say key-level disrespects should NOT flip bias).

Runs run_backtest() twice per instrument/style -- once per
confirmation_source -- against the SAME data snapshot in the SAME
process, so the comparison is apples-to-apples regardless of when the
underlying Dukascopy cache was last refreshed. Trades are filtered to
`--start` onward (default 2025-01-01, i.e. "last year and this year")
by entry_time; all cached history still loads and still drives bias-
building (run_backtest()'s own start_date/end_date semantics).

Usage:
    python -m backtest.engine.compare_confirmation_sources
    python -m backtest.engine.compare_confirmation_sources \
        --start 2025-01-01 --instruments EURUSD,JP225 --styles conservative \
        --json /tmp/comparison.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone

import pandas as pd

from .runner import run_backtest
from .trade_log import summarize
from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS

DEFAULT_EXCLUDE = {"USOIL", "ETHUSD"}  # availability unconfirmed on MetaQuotes-Demo as of writing
SOURCES = ("swing", "key_level")


def _fmt_pct(x):
    return f"{x * 100:.1f}%" if x is not None else "n/a"


def _fmt_r(x):
    return f"{x:+.1f}" if x is not None else "n/a"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-01",
                         help="Only trades entered on/after this date count (YYYY-MM-DD). Default 2025-01-01.")
    parser.add_argument("--instruments", default=None,
                         help="Comma-separated internal symbols. Defaults to all except "
                              f"{sorted(DEFAULT_EXCLUDE)}.")
    parser.add_argument("--styles", default="conservative,aggressive",
                         help="Comma-separated entry styles to run.")
    parser.add_argument("--json", dest="json_path", default=None,
                         help="Also write the full per-instrument/style/source breakdown as JSON.")
    args = parser.parse_args()

    start_date = pd.Timestamp(args.start, tz="UTC")
    instruments = (args.instruments.split(",") if args.instruments
                   else [s for s in DUKASCOPY_INSTRUMENTS if s not in DEFAULT_EXCLUDE])
    styles = args.styles.split(",")

    print(f"Comparing confirmation_source={SOURCES} -- trades entered >= {start_date.date()}")
    print(f"{len(instruments)} instruments x {len(styles)} style(s) x {len(SOURCES)} source(s) = "
          f"{len(instruments) * len(styles) * len(SOURCES)} run_backtest() calls\n")
    sys.stdout.flush()

    rows = []       # per (instrument, style, source)
    totals = {src: {"trades": 0, "wins": 0, "closed": 0, "total_r": 0.0} for src in SOURCES}
    errors = []

    for instrument in instruments:
        for style in styles:
            per_source = {}
            for source in SOURCES:
                try:
                    records = run_backtest(instrument, style, confirmation_source=source)
                except Exception as exc:  # noqa: BLE001 -- one bad instrument shouldn't kill the sweep
                    errors.append({"instrument": instrument, "style": style, "source": source, "error": str(exc)})
                    print(f"  ERROR {instrument} {style} {source}: {exc}")
                    continue
                filtered = [r for r in records if r.entry_time >= start_date]
                stats = summarize(filtered)
                per_source[source] = stats
                totals[source]["trades"] += stats["total_trades"]
                totals[source]["wins"] += stats["wins"]
                totals[source]["closed"] += stats["closed_trades"]
                totals[source]["total_r"] += stats["total_r"]

            if len(per_source) == 2:
                swing, kl = per_source["swing"], per_source["key_level"]
                delta_trades = kl["total_trades"] - swing["total_trades"]
                delta_r = kl["total_r"] - swing["total_r"]
                print(f"{instrument:8s} {style:12s}  swing: {swing['total_trades']:4d} trades, "
                      f"{_fmt_pct(swing['win_rate'])} win, {_fmt_r(swing['total_r'])}R   |   "
                      f"key_level: {kl['total_trades']:4d} trades, {_fmt_pct(kl['win_rate'])} win, "
                      f"{_fmt_r(kl['total_r'])}R   |   Δtrades {delta_trades:+d}  ΔR {delta_r:+.1f}")
                sys.stdout.flush()

            rows.append({"instrument": instrument, "style": style, **per_source})

    print("\n" + "=" * 78)
    print("TOTALS (all instruments/styles combined)")
    print("=" * 78)
    for source in SOURCES:
        t = totals[source]
        win_rate = (t["wins"] / t["closed"]) if t["closed"] else None
        avg_r = (t["total_r"] / t["closed"]) if t["closed"] else None
        print(f"  {source:10s}  trades={t['trades']:5d}  closed={t['closed']:5d}  "
              f"win_rate={_fmt_pct(win_rate)}  total_R={_fmt_r(t['total_r'])}  avg_R={_fmt_r(avg_r)}")

    swing_r, kl_r = totals["swing"]["total_r"], totals["key_level"]["total_r"]
    print(f"\n  total_R delta (key_level - swing): {kl_r - swing_r:+.1f}")
    if errors:
        print(f"\n  {len(errors)} run(s) errored -- see JSON output or scroll up." if args.json_path
              else f"\n  {len(errors)} run(s) errored:")
        if not args.json_path:
            for e in errors:
                print(f"    {e['instrument']} {e['style']} {e['source']}: {e['error']}")

    if args.json_path:
        with open(args.json_path, "w") as f:
            json.dump({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "start_date": str(start_date.date()),
                "instruments": instruments,
                "styles": styles,
                "totals": totals,
                "rows": rows,
                "errors": errors,
            }, f, indent=2, default=str)
        print(f"\nWrote {args.json_path}")


if __name__ == "__main__":
    main()
