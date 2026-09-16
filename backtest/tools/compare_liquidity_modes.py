"""
A/B the two definitions of "single candle liquidity" on real history.

Background (2026-09-16, operator correction, taught via annotated
TradingView charts). The entry path sourced its post-breakout liquidity
pools from `structural_liquidity_points(h4, n=1)` -- a fractal SWING
detector. That is a different concept from SLK's single candle
liquidity, and the two are not interchangeable:

  * sweep of liquidity + break of structure  -> sets directional BIAS.
    StructureTracker owns it. Untouched by this tool.

  * single candle liquidity -> ENTRY TIMING. After a breakout, an
    individual candle leaves its low (buys) or high (sells) behind as a
    resting pool. Price coming back to take it is what delivers price
    into a key level, where a confirmation setup then says which KL is
    real.

A swing detector cannot find the second one. `is_swing_low` needs the
low <= BOTH neighbours, so a post-breakout pullback of higher lows
registers nothing and the search falls back to the breakout candle's own
extreme -- a level price has no reason to revisit.

Worked case, GBPUSD H4 10 Aug 2026 (real cached candles, and the chart
the operator drew by hand):

    12:00  o 1.35008  h 1.35303  l 1.34899  c 1.35254   <- breakout
    16:00  o 1.35254  h 1.35266  l 1.35050  c 1.35077   <- leaves the pool
    20:00  o 1.35077  h 1.35111  l 1.35012  c 1.35105   <- takes it, closes back above

1.35050 is the level. `is_swing_low` cannot return it (1.35050 > the
breakout candle's 1.34899), so the bot armed 1.34899 instead -- 15 pips
below where price actually turned, and never touched again.

Two other fixes ride along in "single_candle" mode and are reported
here as part of the same comparison, because they only matter once the
pools are right:

  * self-sweep: the sweep scan now starts at the pool's CLOSE, so the
    candle that FORMS a low can no longer count as taking it.
  * fall-through: a setup may now offer several reactions, so a
    candidate rejected by a downstream gate (rollover window,
    alignment, IRL/ERL, zone fill, R:R) no longer kills the whole
    setup. Still at most one trade per setup.

Usage (VPS -- real cached data required, this repo checkout has none):

    docker exec -u abc -w /config/trading mt5 nice -n 19 python3 \\
        -m backtest.tools.compare_liquidity_modes \\
        --instruments ALL --start 2026-09-08 --entry-style conservative

Report a `--start` window and it prints, per instrument, the trades each
mode produced inside it and which ones are unique to one mode -- those
are the ones worth pulling up on a chart by hand.
"""

from __future__ import annotations

import argparse
import time
import traceback

import pandas as pd

from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..engine.runner import run_backtest
from ..engine.trade_log import summarize

MODES_DOC = "swing baseline + one single_candle variant per pool cap"


def variants(max_pools_list):
    """The baseline plus one single_candle variant per pool cap.

    Sweeping the cap matters because an over-permissive cap and a wrong
    concept produce the same summary row. The first measured run (cap=6)
    gave 2.3x the trades at a third of the R/trade -- which is what too
    many armed pools looks like, and also what a bad idea looks like.
    Only the sweep tells them apart."""
    out = [("swing", {"liquidity_mode": "swing"})]
    for p in max_pools_list:
        out.append((f"single_candle/{p}",
                    {"liquidity_mode": "single_candle", "single_candle_max_pools": p}))
    for p in max_pools_list:
        out.append((f"sc_h4/{p}",
                    {"liquidity_mode": "single_candle_h4", "single_candle_max_pools": p}))
    return out


def _fmt_price(p):
    return "-" if p is None else f"{p:.5f}"


def _key(rec):
    """Identity for cross-mode comparison: same instrument, same side,
    same entry candle. Price can differ slightly between modes when the
    winning key level differs, so it is reported but not part of the
    key."""
    return (rec.instrument, str(rec.direction), str(rec.entry_time))


def _run(instrument, mode_kwargs, args):
    return run_backtest(
        instrument, args.entry_style,
        **mode_kwargs,
        avoid_rollover_entries=not args.no_avoid_rollover,
        min_reward_r=args.min_reward_r,
        origin_kind=args.origin_kind,
        close_based_sweep_break=not args.wick_based_sweep_break,
        stop_anchor=args.stop_anchor,
    )


def _in_window(rec, start, end):
    t = pd.Timestamp(rec.entry_time)
    # Cached candle times are tz-aware UTC, but don't assume it -- a
    # naive/aware mix raises rather than comparing, which would abort the
    # whole run over a formatting detail.
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    if start is not None and t < start:
        return False
    if end is not None and t > end:
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True,
                        help="comma-separated, or ALL for every Dukascopy instrument")
    parser.add_argument("--entry-style", default="conservative",
                        choices=("aggressive", "conservative"))
    parser.add_argument("--stop-anchor", default="trigger_wick")
    parser.add_argument("--min-reward-r", type=float, default=1.0)
    parser.add_argument("--no-avoid-rollover", action="store_true")
    parser.add_argument("--origin-kind", default="any", choices=("sweep_break", "any"))
    parser.add_argument("--wick-based-sweep-break", action="store_true")
    parser.add_argument("--start", default=None,
                        help="only REPORT trades entered on/after this date "
                             "(full history still loads and drives bias)")
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-pools", default="6",
                        help="comma-separated caps to sweep for single_candle mode, "
                             "e.g. 1,2,3,6. Each runs as its own variant against the "
                             "same swing baseline.")
    args = parser.parse_args()

    pool_caps = [int(x) for x in args.max_pools.split(",") if x.strip()]
    MODES = variants(pool_caps)
    mode_names = [name for name, _ in MODES]

    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]

    start = pd.Timestamp(args.start, tz="UTC") if args.start else None
    end = pd.Timestamp(args.end, tz="UTC") if args.end else None

    totals = {m: {"trades": 0, "r": 0.0, "wins": 0} for m in mode_names}
    unique_rows = []

    for instrument in instruments:
        per_mode = {}
        failed = False
        for mode, mode_kwargs in MODES:
            t0 = time.time()
            try:
                recs = _run(instrument, mode_kwargs, args)
            except FileNotFoundError:
                print(f"{instrument:<9} no cached data, skipped", flush=True)
                failed = True
                break
            except Exception:
                print(f"{instrument:<9} {mode} FAILED:", flush=True)
                traceback.print_exc()
                failed = True
                break
            per_mode[mode] = (recs, time.time() - t0)
        if failed:
            continue

        line = [f"{instrument:<9}"]
        windowed = {}
        for mode in mode_names:
            recs, secs = per_mode[mode]
            s = summarize(recs)
            totals[mode]["trades"] += s.get("closed_trades", 0)
            totals[mode]["r"] += s.get("total_r", 0.0)
            totals[mode]["wins"] += s.get("wins", 0)
            windowed[mode] = [r for r in recs if _in_window(r, start, end)]
            line.append(f"{mode}: {s.get('closed_trades', 0):>5} trades "
                        f"{s.get('total_r', 0.0):>8.1f}R  "
                        f"[{len(windowed[mode])} in window, {secs:.0f}s]")
        print("  ".join(line), flush=True)

        swing_keys = {_key(r) for r in windowed["swing"]}
        for mode in mode_names:
            if mode == "swing":
                continue
            sc_keys = {_key(r) for r in windowed[mode]}
            for r in windowed[mode]:
                if _key(r) not in swing_keys:
                    unique_rows.append((f"{mode} ONLY", r))
            for r in windowed["swing"]:
                if _key(r) not in sc_keys:
                    unique_rows.append((f"swing ONLY (vs {mode})", r))

    print()
    print("=" * 78)
    print("FULL HISTORY TOTALS")
    for mode in mode_names:
        t = totals[mode]
        win = (100.0 * t["wins"] / t["trades"]) if t["trades"] else 0.0
        per = (t["r"] / t["trades"]) if t["trades"] else 0.0
        print(f"  {mode:<18} {t['trades']:>6} trades   {win:>5.1f}% win   "
              f"{t['r']:>9.1f}R   {per:>6.2f} R/trade")
    print()
    print("  R/trade is the column that matters -- more trades at worse quality")
    print("  is how the cap=6 run lost total R while doubling activity.")

    if start is not None or end is not None:
        print()
        print("=" * 78)
        win_desc = f"{args.start or 'start'} .. {args.end or 'now'}"
        print(f"TRADES UNIQUE TO ONE MODE IN {win_desc}")
        print("These are the ones to pull up on a chart and check by hand.")
        print()
        if not unique_rows:
            print("  (none -- both modes produced the same trades in this window)")
        else:
            print(f"  {'mode':<18} {'instrument':<9} {'entry time':<21} {'side':<8} "
                  f"{'entry':>10} {'stop':>10} {'target':>10} {'trigger':<12} {'outcome'}")
            for tag, r in sorted(unique_rows, key=lambda x: str(x[1].entry_time)):
                side = str(getattr(r.direction, "value", r.direction))
                print(f"  {tag:<24} {r.instrument:<9} {str(r.entry_time):<21} {side:<8} "
                      f"{_fmt_price(r.entry_price):>10} {_fmt_price(r.stop_loss):>10} "
                      f"{_fmt_price(r.primary_target):>10} {r.trigger_type:<12} "
                      f"{r.exit_reason or 'still_open'}")


if __name__ == "__main__":
    main()
