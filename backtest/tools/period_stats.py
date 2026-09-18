"""
Per-instrument stats, broken out by period -- trades, win rate, R.

Why this exists rather than `compare_liquidity_modes --start/--end`
(2026-09-18, direct request: "run another backtesting of all the pair
this year and last year data separately, let me see the stats including
win rate"). That tool's `--start/--end` only tag which trades count as
"in window" for its unique-to-one-mode listing; every statistic it
prints is still full-history. There was no way to ask "how did this
strategy do in 2025 versus 2026".

Runs the backtest ONCE per instrument and buckets the resulting trades
by entry time afterwards. Running it once per period instead would
replay the entire history again for each one, for an identical answer --
`run_backtest`'s own `start_date`/`end_date` filter which trades get
RECORDED, they do not narrow the data it reads (deliberately: bias,
alignment and stacking context all need the full series, see that
function's docstring).

A period's numbers are therefore exactly what the strategy produced in
that window while running continuously through everything before it --
not what a bot started on 1 January would have produced, which is a
different and much noisier question.

Usage (VPS -- real cached data required, this checkout has none):

    docker exec -u abc -w /config/trading mt5 nice -n 19 python3 \\
        -m backtest.tools.period_stats --instruments ALL \\
        --periods 2025,2026 --entry-style conservative
"""

from __future__ import annotations

import argparse
import gc
import sys
import time
import traceback

import pandas as pd

from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..engine.runner import run_backtest
from ..engine.trade_log import summarize
from ..engine.trade_management import RISK_REWARD_PRIMARY
from .live_flags import LIVE_FIXED_FLAGS, LIVE_LAUNCH_FLAGS

# Spread is not modelled anywhere in this engine, so every R below is
# gross. This is the rough cost of a round trip on a major, used only to
# print an honest "net" column beside the gross one -- not applied to
# any decision, and deliberately a single number rather than a
# per-instrument table nobody has measured.
ASSUMED_SPREAD_R = 0.12


def parse_periods(raw: str):
    """"2025,2026" or "2025-01-01:2025-06-30" -- a bare year expands to
    that whole calendar year."""
    out = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            lo, hi = item.split(":", 1)
            out.append((item, pd.Timestamp(lo, tz="UTC"),
                        pd.Timestamp(hi, tz="UTC") + pd.Timedelta(days=1)))
        else:
            year = int(item)
            out.append((item, pd.Timestamp(f"{year}-01-01", tz="UTC"),
                        pd.Timestamp(f"{year + 1}-01-01", tz="UTC")))
    return out


def bucket(records, start, end):
    """Trades whose ENTRY falls in [start, end). Entry, not exit: a trade
    belongs to the period it was decided in, which is the period whose
    conditions produced it."""
    out = []
    for r in records:
        t = pd.Timestamp(r.entry_time)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        if start <= t < end:
            out.append(r)
    return out


HEADER = (f"  {'period':<12} {'trades':>6} {'win':>7} {'total':>9} "
          f"{'R/trade':>8} {'net':>7} {'avgWin':>7} {'avgLoss':>8} {'capped':>7}")


def _row(label, recs):
    """One period's numbers.

    avgWin / capped exist to explain R/trade rather than leave it
    mysterious. The engine targets 3:1 (RISK_REWARD_PRIMARY) but caps
    every target at the nearest external range liquidity, so realized
    wins are routinely well under 3R -- asked directly on 2026-09-18,
    "is the backtest not targeting a 3:1?", which the previous columns
    gave no way to answer. `capped` is the share of trades where the ERL
    cap actually moved the target in from 3:1, and it went UP with the
    2026-09-18 sweep fix: requiring the sweeping period to have CLOSED
    leaves more liquidity standing, so more targets get pulled in."""
    s = summarize(recs)
    closed = s.get("closed_trades", 0)
    total_r = s.get("total_r", 0.0)
    win = 100.0 * s["win_rate"] if s.get("win_rate") is not None else 0.0
    if not closed:
        # Dashes, not zeros. A period with no trades printing
        # "0.0% win, 0.00 R/trade, -0.12 net" reads as a measured result
        # rather than an absence of one, and that column would appear on
        # every quiet pair in a 25-instrument run.
        return (f"  {label:<12} {0:>6} {'-':>7} {'-':>9} "
                f"{'-':>8} {'-':>7} {'-':>7} {'-':>8} {'-':>7}")
    per = total_r / closed
    done = [r for r in recs if r.r_multiple is not None]
    wins = [r.r_multiple for r in done if r.r_multiple > 0]
    losses = [r.r_multiple for r in done if r.r_multiple <= 0]
    capped = [r for r in done if getattr(r, "erl_capped", False)]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    capped_pct = 100.0 * len(capped) / len(done) if done else 0.0
    return (f"  {label:<12} {closed:>6} {win:>6.1f}% {total_r:>8.1f}R "
            f"{per:>8.2f} {per - ASSUMED_SPREAD_R:>7.2f} "
            f"{avg_win:>7.2f} {avg_loss:>8.2f} {capped_pct:>6.0f}%")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instruments", required=True, help="comma-separated, or ALL")
    ap.add_argument("--periods", default="2025,2026",
                    help="comma-separated years or FROM:TO ranges (default 2025,2026)")
    ap.add_argument("--entry-style", default="conservative",
                    choices=("aggressive", "conservative"))
    ap.add_argument("--source", default="dukascopy")
    ap.add_argument("--stop-anchor", default=LIVE_LAUNCH_FLAGS["stop_anchor"])
    ap.add_argument("--origin-kind", default=LIVE_LAUNCH_FLAGS["origin_kind"],
                    choices=("sweep_break", "any"))
    ap.add_argument("--wick-based-sweep-break", dest="close_based_sweep_break",
                    action="store_false",
                    default=LIVE_LAUNCH_FLAGS["close_based_sweep_break"],
                    help="turn OFF close-based sweep breaks, which the live bots run WITH")
    args = ap.parse_args()

    sys.stdout.reconfigure(line_buffering=True)
    periods = parse_periods(args.periods)

    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]

    print(f"style={args.entry_style}   periods={[p[0] for p in periods]}")
    print("flags: " + "  ".join(f"{k}={v}" for k, v in LIVE_FIXED_FLAGS.items())
          + f"  origin_kind={args.origin_kind}"
          + f"  close_based_sweep_break={args.close_based_sweep_break}"
          + f"  stop_anchor={args.stop_anchor}")
    print(f"net R/trade assumes {ASSUMED_SPREAD_R} R of spread per round trip -- the engine")
    print("models none, so the gross column is what it actually computed.")
    print(f"targets are {RISK_REWARD_PRIMARY:g}:1 CAPPED at the nearest external range liquidity,")
    print("so avgWin sits below that; `capped` is how often the cap actually bound.")
    print()

    pooled = {label: [] for label, _, _ in periods}
    pooled["all-time"] = []

    for instrument in instruments:
        t0 = time.time()
        try:
            records = run_backtest(instrument, args.entry_style, source=args.source,
                                   **LIVE_FIXED_FLAGS,
                                   stop_anchor=args.stop_anchor,
                                   origin_kind=args.origin_kind,
                                   close_based_sweep_break=args.close_based_sweep_break)
        except FileNotFoundError:
            print(f"{instrument}: no cached data")
            continue
        except Exception:
            print(f"{instrument}: FAILED after {time.time() - t0:.0f}s")
            traceback.print_exc()
            continue

        print(f"{instrument}   ({len(records)} trades all-time, {time.time() - t0:.0f}s)")
        print(HEADER)
        for label, start, end in periods:
            recs = bucket(records, start, end)
            pooled[label].extend(recs)
            print(_row(label, recs))
        pooled["all-time"].extend(records)
        print(_row("all-time", records))
        print()

        del records
        gc.collect()

    print("=" * 62)
    print("ALL INSTRUMENTS POOLED")
    print(HEADER)
    for label, _s, _e in periods:
        print(_row(label, pooled[label]))
    print(_row("all-time", pooled["all-time"]))


if __name__ == "__main__":
    main()
