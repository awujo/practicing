"""
Repair H4/D/W cache series polluted by bars from a different anchor.

What happened (2026-08-19 to 2026-09-16). `bot/live_cache_sync.py`
appended MT5's H4/D/W bars onto the Dukascopy series. MT5 anchors bars
to BROKER midnight -- the server runs UTC+3, so its H4 bars fall on
01/05/09/13/17/21 UTC, its daily bars on 21:00 UTC, its weekly bars on
Saturday 21:00 UTC (confirmed against the live terminal for every FX
pair and both metals). Dukascopy anchors to UTC midnight: 00/04/08/12/
16/20, daily at 00:00, weekly Monday 00:00.

Those are two different series. Interleaving them yields bars covering
overlapping spans of time, and `cache.append()` dedupes by TIMESTAMP so
it cannot notice -- a 16:00 bar and a 17:00 bar are two different
timestamps, both entirely plausible.

Measured damage before repair:

    GBPUSD H4   clean [0,4,8,12,16,20] every month through 2026-07, then
                all 24 hours. 203 rows in August vs a normal ~136. 173
                rows closer than one bar to the row before. 0 exact
                duplicates -- which is precisely why nothing caught it.
    GBPUSD D    26 rows/month through 2026-07, then 162 in August.
                2026-09 had no midnight bars at all.
    XAUUSD      same shape, same months.

H1 is NOT affected and is the source this rebuilds from. Verified by
lag-matching cached H1 closes against the live terminal's H1 across ~700
bars: lag 0 wins by 40x on GBPUSD (median |close diff| 0.00001 vs
0.00039 at +/-1h) and 60x on XAUUSD (0.12 vs 7.37). An H1 bar is an H1
bar on either feed, because the broker offset is a whole number of
hours.

The rebuild uses the UTC-midnight anchor, matching the twenty-plus years
of clean Dukascopy history already in the file. That makes this a
restoration, not a redesign. Whether the engine should instead run on
the broker's own anchor is a real and separate question -- it is what
MT5 actually fills against -- but it changes every backtest number ever
produced and must be settled by its own A/B, with DST handled properly
(the server is UTC+3 in summer and UTC+2 in winter, so a fixed origin
would be wrong half the year). Do not conflate the two.

Usage (VPS). Dry run first -- it reports and changes nothing:

    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.repair_cache_grid --instruments ALL

Then, with the bots stopped so nothing re-poisons the file mid-repair:

    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.repair_cache_grid --instruments ALL --apply
"""

from __future__ import annotations

import argparse
import traceback

import pandas as pd

from ..data_pipeline import cache
from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..data_pipeline.resample import REPAIRABLE_GRANULARITIES, resample_ohlcv

# The grid a clean, UTC-anchored Dukascopy series sits on.
CLEAN_GRID = {
    "H4": {"hours": [0, 4, 8, 12, 16, 20], "dow": None},
    "D": {"hours": [0], "dow": None},
    "W": {"hours": [0], "dow": [0]},  # Monday
}

# Rows at or after this are rebuilt. The first off-grid row observed was
# 2026-08-11 (daily), so this starts comfortably before it -- rebuilding
# a few extra clean bars from H1 is harmless, missing a poisoned one is
# not. Overridable with --cutoff.
DEFAULT_CUTOFF = "2026-08-01T00:00:00Z"


def _off_grid(times: pd.Series, granularity: str) -> pd.Series:
    spec = CLEAN_GRID[granularity]
    bad = ~times.dt.hour.isin(spec["hours"])
    if spec["dow"] is not None:
        bad |= ~times.dt.dayofweek.isin(spec["dow"])
    return bad


def _overlapping(times: pd.Series, granularity: str) -> int:
    """Rows sitting closer to the previous row than one whole bar --
    the actual damage, as distinct from merely being off-grid."""
    step = {"H4": 4, "D": 24, "W": 24 * 7}[granularity]
    gaps = times.sort_values().diff().dropna().dt.total_seconds() / 3600
    return int((gaps < step).sum())


def inspect(source: str, symbol: str, granularity: str):
    df = cache.load(source, symbol, granularity)
    t = pd.to_datetime(df["time"], utc=True).sort_values()
    bad = _off_grid(t, granularity)
    return {
        "rows": len(t),
        "off_grid": int(bad.sum()),
        "overlapping": _overlapping(t, granularity),
        "first_bad": t[bad].min() if bad.any() else None,
        "hours": sorted(t.dt.hour.unique().tolist()),
    }


def rebuild(source: str, symbol: str, granularity: str, cutoff: str, apply: bool):
    """Re-derive `granularity` from H1 for everything at/after `cutoff`."""
    src_name, rule, kwargs = REPAIRABLE_GRANULARITIES[granularity]
    h1 = cache.load(source, symbol, src_name)
    h1 = h1.copy()
    h1["time"] = pd.to_datetime(h1["time"], utc=True)

    cut = pd.Timestamp(cutoff)
    # Resample from a bar boundary BEFORE the cutoff, not from the cutoff
    # itself: a bin that straddles the boundary must see all of its H1
    # rows or its open/high/low/close are computed from a partial bar.
    lead = {"H4": pd.Timedelta(days=2), "D": pd.Timedelta(days=2),
            "W": pd.Timedelta(days=14)}[granularity]
    window = h1[h1["time"] >= cut - lead]
    if window.empty:
        return None

    out = resample_ohlcv(window, rule, **kwargs)
    out = out[out["time"] >= cut]
    rows = [
        {"time": r["time"].isoformat().replace("+00:00", "Z"),
         "open": r["open"], "high": r["high"], "low": r["low"],
         "close": r["close"], "volume": r["volume"]}
        for _, r in out.iterrows()
    ]
    if not apply:
        return {"would_write": len(rows)}
    dropped, written = cache.replace_from(source, symbol, granularity, cutoff, rows)
    return {"dropped": dropped, "written": written}


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True,
                        help="comma-separated, or ALL")
    parser.add_argument("--source", default="dukascopy")
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF,
                        help=f"rebuild rows at/after this ISO time (default {DEFAULT_CUTOFF})")
    parser.add_argument("--granularities", default="H4,D,W")
    parser.add_argument("--apply", action="store_true",
                        help="actually rewrite the cache. Without this, reports only. "
                             "STOP THE BOTS FIRST -- the live sync appends every hour "
                             "and would re-poison the file mid-repair.")
    args = parser.parse_args()

    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    grans = [g.strip() for g in args.granularities.split(",") if g.strip()]

    if not args.apply:
        print("DRY RUN -- nothing will be written. Re-run with --apply to repair.\n")

    totals = {"off_grid": 0, "overlapping": 0, "dropped": 0, "written": 0}
    for symbol in instruments:
        for g in grans:
            try:
                before = inspect(args.source, symbol, g)
            except FileNotFoundError:
                print(f"{symbol:<9} {g:<3} no cache, skipped")
                continue
            except Exception:
                print(f"{symbol:<9} {g:<3} INSPECT FAILED:")
                traceback.print_exc()
                continue

            totals["off_grid"] += before["off_grid"]
            totals["overlapping"] += before["overlapping"]
            status = (f"{symbol:<9} {g:<3} {before['rows']:>6} rows  "
                      f"off_grid={before['off_grid']:<5} overlapping={before['overlapping']:<5}")
            if before["off_grid"] == 0 and before["overlapping"] == 0:
                print(status + "  CLEAN")
                continue
            status += f"  first_bad={before['first_bad']}"

            try:
                result = rebuild(args.source, symbol, g, args.cutoff, args.apply)
            except Exception:
                print(status + "  REBUILD FAILED:")
                traceback.print_exc()
                continue
            if result is None:
                print(status + "  no H1 in range, SKIPPED")
                continue

            if not args.apply:
                print(status + f"  -> would rebuild {result['would_write']} rows from H1")
                continue

            totals["dropped"] += result["dropped"]
            totals["written"] += result["written"]
            after = inspect(args.source, symbol, g)
            verdict = "CLEAN" if (after["off_grid"] == 0 and after["overlapping"] == 0) else "STILL DIRTY"
            print(status + f"  -> dropped {result['dropped']}, wrote {result['written']}, "
                           f"now off_grid={after['off_grid']} overlapping={after['overlapping']} {verdict}")

    print()
    print(f"off-grid rows found: {totals['off_grid']}, overlapping rows found: {totals['overlapping']}")
    if args.apply:
        print(f"dropped: {totals['dropped']}, rebuilt from H1: {totals['written']}")
    else:
        print("Nothing was written. Re-run with --apply (bots stopped) to repair.")


if __name__ == "__main__":
    main()
