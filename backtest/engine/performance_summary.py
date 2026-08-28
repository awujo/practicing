"""
Aggregate backtest performance across the instrument set -- a plain
run_backtest() sweep, no A/B flag. Built 2026-08-28 to (1) report the
current engine's performance over a given window (e.g. "the current live
bot version's 2-year performance"), and (2) serve as a stable driver
script for before/after comparisons across commits: this script's own
interface doesn't change, so a workflow can `git checkout <old_sha> --
backtest/engine/{bias,structure,key_levels,liquidity,runner}.py` to swap
in an older engine, rerun this same script, and diff the JSON output
against a run of the current engine -- see
.github/workflows/compare-lookahead-fix.yml for exactly that use.

Usage:
    python -m backtest.engine.performance_summary
    python -m backtest.engine.performance_summary \
        --start 2025-01-01 --instruments EURUSD,JP225 --styles conservative \
        --json /tmp/summary.json
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
                         help="Also write the full per-instrument/style breakdown as JSON.")
    args = parser.parse_args()

    start_date = pd.Timestamp(args.start, tz="UTC")
    instruments = (args.instruments.split(",") if args.instruments
                   else [s for s in DUKASCOPY_INSTRUMENTS if s not in DEFAULT_EXCLUDE])
    styles = args.styles.split(",")

    print(f"Performance summary -- trades entered >= {start_date.date()}")
    print(f"{len(instruments)} instruments x {len(styles)} style(s) = {len(instruments) * len(styles)} run_backtest() calls\n")
    sys.stdout.flush()

    rows = []
    totals = {"trades": 0, "wins": 0, "closed": 0, "total_r": 0.0}
    errors = []

    for instrument in instruments:
        for style in styles:
            try:
                records = run_backtest(instrument, style)
            except Exception as exc:  # noqa: BLE001 -- one bad instrument shouldn't kill the sweep
                errors.append({"instrument": instrument, "style": style, "error": str(exc)})
                print(f"  ERROR {instrument} {style}: {exc}")
                continue
            filtered = [r for r in records if r.entry_time >= start_date]
            stats = summarize(filtered)
            totals["trades"] += stats["total_trades"]
            totals["wins"] += stats["wins"]
            totals["closed"] += stats["closed_trades"]
            totals["total_r"] += stats["total_r"]
            print(f"{instrument:8s} {style:12s}  {stats['total_trades']:4d} trades, "
                  f"{_fmt_pct(stats['win_rate'])} win, {_fmt_r(stats['total_r'])}R")
            sys.stdout.flush()
            rows.append({"instrument": instrument, "style": style, **stats})

    win_rate = (totals["wins"] / totals["closed"]) if totals["closed"] else None
    avg_r = (totals["total_r"] / totals["closed"]) if totals["closed"] else None

    print("\n" + "=" * 78)
    print("TOTAL (all instruments/styles combined)")
    print("=" * 78)
    print(f"  trades={totals['trades']:5d}  closed={totals['closed']:5d}  "
          f"win_rate={_fmt_pct(win_rate)}  total_R={_fmt_r(totals['total_r'])}  avg_R={_fmt_r(avg_r)}")
    if errors:
        print(f"\n  {len(errors)} run(s) errored -- see JSON output." if args.json_path
              else f"\n  {len(errors)} run(s) errored:")
        if not args.json_path:
            for e in errors:
                print(f"    {e['instrument']} {e['style']}: {e['error']}")

    if args.json_path:
        with open(args.json_path, "w") as f:
            json.dump({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "start_date": str(start_date.date()),
                "instruments": instruments,
                "styles": styles,
                "totals": totals,
                "win_rate": win_rate,
                "avg_r": avg_r,
                "rows": rows,
                "errors": errors,
            }, f, indent=2, default=str)
        print(f"\nWrote {args.json_path}")


if __name__ == "__main__":
    main()
