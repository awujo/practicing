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

`find_minimum_safe_window()` runs the operator's own proposed process for
real: start at the given windows; if they don't reproduce full history's
recent trades, extend both by their step size and try again, stopping at
the first window size that matches (or a max-years cap, to admit defeat
rather than loop forever). Confirmed live 2026-09-13 that a FIXED window
is not safe across instruments: perfect for US30 at 2y/1y, subtly wrong
for EURUSD (same trade COUNT, 6 different trades from a bias that quietly
drifted -- a bare empty-check would have missed this entirely), and
completely empty for GBPJPY (no confirmed structure found at all within
that window) -- exactly the case escalation exists for.

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


def windowed_loader(windows_days: dict, recent_days: float = 0):
    """Returns a stand-in for candles.load_candles() that serves only a
    trailing slice of a real load, anchored to the DATA's own newest
    candle (not wall-clock "now").

    `recent_days` extends every configured window further back by the
    length of the comparison period itself, and it is NOT optional for a
    correct test. Without it, a trade whose entry is `recent_days` old
    would only see `windows_days[gran]` days of history ending AT TODAY
    -- (today - window) to today -- most of which POSTDATES that trade
    and none of which it could actually have seen at the time. What it
    needs is a `window`-day runway ending AT ITS OWN entry time --
    (entry - window) to entry. Caught directly by the operator (2026-09-13):
    "for a trade 2 years ago it will start from 4 years ago" -- i.e. the
    window PLUS the recency of the trade being checked, not the window
    alone. Retaining (window + recent_days) and letting run_backtest()
    walk the whole slice CONTINUOUSLY from that one bootstrap point
    onward gives every trade in the comparison period at least its full
    window's worth of real prior history, and is also the more realistic
    thing to simulate: a live bot given a bounded initial backfill that
    then keeps growing forward normally (this codebase's cache only ever
    appends, never prunes), not a bot that continuously forgets old
    candles as it goes -- nobody has asked for that, and it would need
    the confirmation/bias state machines to periodically reset, a much
    bigger change than this test is checking.

    A granularity with no configured window (or fewer candles than the
    combined slice) passes through untouched."""
    def _load(source: str, symbol: str, granularity: str) -> list[Candle]:
        candles = real_load_candles(source, symbol, granularity)
        window = windows_days.get(granularity)
        if not window or not candles:
            return candles
        cutoff = candles[-1].time - pd.Timedelta(days=window + recent_days)
        return [c for c in candles if c.time >= cutoff]
    return _load


def run_variant(instrument: str, entry_style: str, stop_anchor: str,
                 windows_days: dict | None, recent_days: float = 0, **kwargs):
    """Runs run_backtest() once, patched to the given trailing windows if
    any (None/{} = the real, full-history behavior, unpatched). Returns
    (records, elapsed_seconds). See windowed_loader() for why recent_days
    must match whatever comparison period the caller will diff against."""
    if windows_days:
        with mock.patch.object(runner_module, "load_candles", windowed_loader(windows_days, recent_days)):
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


def find_minimum_safe_window(instrument: str, entry_style: str, stop_anchor: str,
                              dw_years: float, h_years: float,
                              dw_step_years: float, h_step_years: float,
                              max_years: float, recent_years: float,
                              baseline=None, baseline_secs: float = 0.0, **kwargs) -> dict:
    """Runs the operator's own proposed process for real: start at
    (dw_years, h_years); if the truncated run does not reproduce every
    recent-period trade full history produces, extend both windows by
    their step size and try again; stop once it matches, or once
    dw_years exceeds max_years (give up rather than loop forever).

    Critically, "does not reproduce" is judged against full history's
    ACTUAL trades, not just whether the truncated run produced anything
    at all -- a bare empty-check cannot catch a truncated window that
    produces the SAME COUNT of trades but different ones (confirmed
    live, EURUSD, 2026-09-13: 78 trades both ways, 6 of them not the
    same trades). Convergence here means genuinely identical, not
    merely non-empty.

    `baseline`/`baseline_secs` let a caller iterating several configs
    reuse one already-computed full-history run instead of recomputing
    the expensive part every time; omit them to compute it here."""
    if baseline is None:
        baseline, baseline_secs = run_variant(instrument, entry_style, stop_anchor, None, **kwargs)
    if not baseline:
        return {"instrument": instrument, "baseline_secs": baseline_secs, "baseline_count": 0,
                "converged": False, "dw_years": None, "h_years": None, "steps": []}

    source = kwargs.get("source", "dukascopy")
    newest = max(c.time for c in real_load_candles(source, instrument, "H1"))
    recent_cutoff = newest - pd.Timedelta(days=recent_years * 365)

    steps = []
    dw, h = dw_years, h_years
    while dw <= max_years:
        windows_days = {"D": dw * 365, "W": dw * 365, "H4": h * 365, "H1": h * 365}
        variant, variant_secs = run_variant(instrument, entry_style, stop_anchor, windows_days,
                                             recent_days=recent_years * 365, **kwargs)
        result = diff_recent(baseline, variant, recent_cutoff)
        converged = not result["only_in_baseline"] and not result["only_in_variant"]
        steps.append({"dw_years": dw, "h_years": h, "variant_secs": variant_secs,
                       "converged": converged, **result})
        if converged:
            return {"instrument": instrument, "baseline_secs": baseline_secs,
                     "baseline_count": len(baseline), "converged": True,
                     "dw_years": dw, "h_years": h, "steps": steps}
        dw += dw_step_years
        h += h_step_years

    return {"instrument": instrument, "baseline_secs": baseline_secs,
             "baseline_count": len(baseline), "converged": False,
             "dw_years": None, "h_years": None, "steps": steps}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True, help="comma-separated, e.g. EURUSD,GBPJPY")
    parser.add_argument("--entry-style", default="aggressive", choices=("aggressive", "conservative"))
    parser.add_argument("--stop-anchor", default="trigger_wick", choices=("trigger_wick", "structural"))
    parser.add_argument("--dw-years", type=float, default=2.0,
                         help="starting trailing window, in years, for Daily/Weekly candles")
    parser.add_argument("--h-years", type=float, default=1.0,
                         help="starting trailing window, in years, for H4/H1 candles")
    parser.add_argument("--dw-step-years", type=float, default=1.0,
                         help="how much to extend the Daily/Weekly window by, per escalation step, "
                              "when the current one does not reproduce full history's recent trades")
    parser.add_argument("--h-step-years", type=float, default=0.5,
                         help="how much to extend the H4/H1 window by, per escalation step")
    parser.add_argument("--max-years", type=float, default=15.0,
                         help="give up escalating once the Daily/Weekly window would exceed this -- "
                              "a safety bound against looping forever on an instrument that never "
                              "converges within a sane amount of history")
    parser.add_argument("--recent-years", type=float, default=2.0,
                         help="only trades whose entry falls within this many years of the newest "
                              "cached candle are compared -- older history is irrelevant to whether "
                              "the live bot would decide differently today")
    parser.add_argument("--min-reward-r", type=float, default=1.0)
    parser.add_argument("--no-avoid-rollover", action="store_true")
    args = parser.parse_args()

    instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    common_kwargs = dict(avoid_rollover_entries=not args.no_avoid_rollover, min_reward_r=args.min_reward_r)

    for instrument in instruments:
        print(f"=== {instrument} ===", flush=True)

        report = find_minimum_safe_window(
            instrument, args.entry_style, args.stop_anchor,
            args.dw_years, args.h_years, args.dw_step_years, args.h_step_years,
            args.max_years, args.recent_years, **common_kwargs,
        )
        print(f"  full history:      {report['baseline_count']:5d} trades in {report['baseline_secs']:6.1f}s",
              flush=True)
        if report["baseline_count"] == 0:
            print("  (no trades at all -- skipping, nothing to compare)", flush=True)
            continue

        for step in report["steps"]:
            status = "CONVERGED" if step["converged"] else "not yet -- escalating"
            print(f"  D/W={step['dw_years']:.1f}y H4/H1={step['h_years']:.1f}y: "
                  f"{step['variant_count']:4d} trades in {step['variant_secs']:5.1f}s, "
                  f"{step['matched']}/{step['baseline_count']} match -- {status}", flush=True)
            if not step["converged"]:
                for r in step["only_in_baseline"]:
                    print(f"      only in FULL history:      {_fmt_trade(r)}", flush=True)
                for r in step["only_in_variant"]:
                    print(f"      only in TRUNCATED window:  {_fmt_trade(r)}", flush=True)

        if report["converged"]:
            print(f"  RESULT: D/W={report['dw_years']:.1f}y, H4/H1={report['h_years']:.1f}y "
                  f"reproduces every recent trade exactly.", flush=True)
        else:
            print(f"  RESULT: never converged within the {args.max_years}y cap -- "
                  f"this instrument needs more history than the escalation ceiling allows.", flush=True)
        print(flush=True)


if __name__ == "__main__":
    main()
