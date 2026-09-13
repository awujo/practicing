"""
Does the live bot need candle history back to 2003 to get TODAY'S
decisions right, or would a bounded trailing window produce the exact
same RECENT trades at a fraction of the replay cost?

Motivation (operator, 2026-09-13), verbatim: "we don't need data up to
2003 to know what a pair is currently on... 2 years [worth of Weekly/
Daily candles can tell you what you want]... unless it doesn't [confirm
a bias], then the system can add an extra year... For the 4H to the 1H
down... a year['s worth]... if it doesn't, add extra 6 months."

This is the unfinished half of an earlier fix in this project (see
OPERATIONS_LOG.md: "no check needs 2003's H1 candles re-walked to know
what the current H1 just did" -- sketched as "warm up once from full
history, checkpoint to disk, then feed one candle at a time," never
built). It is also explicitly warned against in run_backtest()'s own
docstring: "start_date/end_date is NOT a data-loading window... narrowing
the loaded data itself would silently break bias-building, alignment,
and stacking context." So this is tested here, not assumed either way.

Method: monkeypatch the candle loader `run_backtest()` itself calls so it
serves only a trailing window per granularity (Daily/Weekly get one
window, H4/H1 another -- matching how the strategy actually separates
them), run `run_backtest()` both with and without the patch, and diff
every trade whose entry falls in the RECENT period (the only one that
matters live) between the two runs. Identical trades in that period means
the truncation is safe at that window size; any mismatch shows exactly
which decision changed and why -- not just that something did.

Needs real cached data (the VPS); this repo checkout has none, so running
it here always reports "0 trades in either run" rather than a real
answer.
"""

from __future__ import annotations

import argparse
import time
from unittest import mock

import pandas as pd

from ..engine import runner as runner_module
from ..engine.candles import Candle, load_candles as real_load_candles
from ..engine.runner import run_backtest

# What makes two runs' trades "the same decision." Deliberately excludes
# bookkeeping fields that can legitimately differ without the underlying
# decision being wrong: trade_id (just a counter), ranking_score and
# concurrent_open_positions_at_entry (both depend on what ELSE fired in
# the same run, not on whether THIS decision was right).
COMPARE_FIELDS = (
    "instrument", "entry_time", "direction", "entry_price", "stop_loss",
    "primary_target", "trigger_type", "exit_reason", "r_multiple", "status",
)


def windowed_loader(windows_days: dict):
    """Returns a stand-in for candles.load_candles() that serves only the
    trailing `windows_days[granularity]` days of a real load, anchored to
    the DATA's own newest candle (not wall-clock "now") -- this must
    reproduce what a rolling live window would actually see, and a real
    cache's newest candle is always close to now anyway. A granularity
    with no configured window (or fewer candles than the window) passes
    through untouched."""
    def _load(source: str, symbol: str, granularity: str) -> list[Candle]:
        candles = real_load_candles(source, symbol, granularity)
        window = windows_days.get(granularity)
        if not window or not candles:
            return candles
        cutoff = candles[-1].time - pd.Timedelta(days=window)
        return [c for c in candles if c.time >= cutoff]
    return _load


def run_variant(instrument: str, entry_style: str, stop_anchor: str,
                 windows_days: dict | None, **kwargs):
    """Runs run_backtest() once, patched to the given trailing windows if
    any (None/{} = the real, full-history behavior, unpatched). Returns
    (records, elapsed_seconds)."""
    if windows_days:
        with mock.patch.object(runner_module, "load_candles", windowed_loader(windows_days)):
            start = time.monotonic()
            records = run_backtest(instrument, entry_style, stop_anchor=stop_anchor, **kwargs)
            elapsed = time.monotonic() - start
    else:
        start = time.monotonic()
        records = run_backtest(instrument, entry_style, stop_anchor=stop_anchor, **kwargs)
        elapsed = time.monotonic() - start
    return records, elapsed


def _key(record) -> tuple:
    return tuple(getattr(record, f) for f in COMPARE_FIELDS)


def diff_recent(baseline: list, variant: list, recent_cutoff) -> dict:
    """Compares only trades whose entry_time is at/after `recent_cutoff`
    -- the ancient end of a multi-decade backtest is not what live
    trading cares about, and isn't what a bounded window claims to
    reproduce anyway."""
    baseline_recent = {_key(r): r for r in baseline if r.entry_time >= recent_cutoff}
    variant_recent = {_key(r): r for r in variant if r.entry_time >= recent_cutoff}
    only_baseline = [r for k, r in baseline_recent.items() if k not in variant_recent]
    only_variant = [r for k, r in variant_recent.items() if k not in baseline_recent]
    return {
        "baseline_count": len(baseline_recent),
        "variant_count": len(variant_recent),
        "matched": len(baseline_recent) - len(only_baseline),
        "only_in_baseline": only_baseline,
        "only_in_variant": only_variant,
    }


def _fmt_trade(r) -> str:
    return (f"{r.entry_time} {r.instrument} {r.direction} entry={r.entry_price} "
            f"stop={r.stop_loss} target={r.primary_target} -> {r.exit_reason}/{r.r_multiple}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True, help="comma-separated, e.g. EURUSD,GBPJPY")
    parser.add_argument("--entry-style", default="aggressive", choices=("aggressive", "conservative"))
    parser.add_argument("--stop-anchor", default="trigger_wick", choices=("trigger_wick", "structural"))
    parser.add_argument("--dw-years", type=float, default=2.0,
                         help="trailing window, in years, for Daily/Weekly candles in the truncated run")
    parser.add_argument("--h-years", type=float, default=1.0,
                         help="trailing window, in years, for H4/H1 candles in the truncated run")
    parser.add_argument("--recent-years", type=float, default=2.0,
                         help="only trades whose entry falls within this many years of the newest "
                              "cached candle are compared -- older history is irrelevant to whether "
                              "the live bot would decide differently today")
    parser.add_argument("--min-reward-r", type=float, default=1.0)
    parser.add_argument("--no-avoid-rollover", action="store_true")
    args = parser.parse_args()

    instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    windows_days = {
        "D": args.dw_years * 365, "W": args.dw_years * 365,
        "H4": args.h_years * 365, "H1": args.h_years * 365,
    }
    common_kwargs = dict(avoid_rollover_entries=not args.no_avoid_rollover, min_reward_r=args.min_reward_r)

    for instrument in instruments:
        print(f"=== {instrument} ===", flush=True)

        baseline, baseline_secs = run_variant(instrument, args.entry_style, args.stop_anchor,
                                               None, **common_kwargs)
        print(f"  full history:      {len(baseline):5d} trades in {baseline_secs:6.1f}s", flush=True)
        if not baseline:
            print("  (no trades at all -- skipping, nothing to compare)", flush=True)
            continue

        variant, variant_secs = run_variant(instrument, args.entry_style, args.stop_anchor,
                                             windows_days, **common_kwargs)
        speedup = f"{baseline_secs / variant_secs:.1f}x faster" if variant_secs > 0 else "effectively instant"
        print(f"  D/W={args.dw_years}y H4/H1={args.h_years}y: {len(variant):5d} trades in "
              f"{variant_secs:6.1f}s ({speedup})", flush=True)

        newest = max(c.time for c in real_load_candles("dukascopy", instrument, "H1"))
        recent_cutoff = newest - pd.Timedelta(days=args.recent_years * 365)
        result = diff_recent(baseline, variant, recent_cutoff)
        print(f"  recent ({args.recent_years}y) window: {result['baseline_count']} baseline trades, "
              f"{result['variant_count']} truncated trades, {result['matched']} match exactly", flush=True)

        if result["only_in_baseline"] or result["only_in_variant"]:
            print("  MISMATCHES:", flush=True)
            for r in result["only_in_baseline"]:
                print(f"    only in FULL history:      {_fmt_trade(r)}", flush=True)
            for r in result["only_in_variant"]:
                print(f"    only in TRUNCATED window:  {_fmt_trade(r)}", flush=True)
        else:
            print("  IDENTICAL -- the truncated window reproduces every recent trade exactly.", flush=True)
        print(flush=True)


if __name__ == "__main__":
    main()
