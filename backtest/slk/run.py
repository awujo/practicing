"""
Run the replay on cached data and print what it did.

    docker exec -u abc -w /config/trading mt5 nice -n 19 python3 \
        -m backtest.slk.run --instrument EURUSD --n 2 --spread 1.0

It is python3 in that container, not python, and `nice` because the live
bots share the box.

There is no default for `--n`. The course never defines a swing
numerically, so the width is a number I chose and every caller has to say
which one it is using -- the same reason `LevelStream(n)` will not
compile without it. Sweeping it (`--n 1 --n 2 --n 3`) is how the system's
dependence on it gets MEASURED instead of assumed.

WHAT THE NUMBERS DO AND DO NOT INCLUDE

Gross R is the sum of each trade's own R, where R is the distance to that
trade's stop. Spread is charged per trade against that trade's own risk,
`spread_pips / risk_pips`, because a flat 0.12R per round trip silently
assumes every trade risks the same distance and they do not -- a trade
risking 0.2 pips on a 1.5-pip spread pays 7.5R, not 0.12R. Slippage is
not modelled at all, and neither is a fill simulation: a bar that touched
a price is assumed to have filled there.

`ambiguous` counts trades where one bar reached both the entry and the
stop. Four numbers per candle cannot say which came first, so those are
assumed filled-then-stopped. If that count is a large share of the
losses, the result rests on the assumption and you should know it; if it
is small, it does not matter and the number says so.

`open at end` are positions still live when the data ran out. They are
excluded from every figure rather than marked to market, because marking
them would let the last few bars of the series decide the result.

WHAT THIS CANNOT YET SETTLE

The 5.1 question -- whether the shallow mitigation depth is worth trading
instead of the open-close level -- is NOT reported here, and a first
attempt at it was removed rather than shipped. Every engulf order carries
both depths, so it is tempting to recompute each trade's R at the
shallower entry. That number is systematically biased and would flatter
the shallow depth every time: a loser loses exactly 1R either way, while a
winner's R rises because the risk shrank. The trades it would MISS are the
ones where price turned at the shallow depth, filled there, and then
stopped out -- setups where the deeper order never filled at all and so
never appears in this table.

Settling it needs order-level accounting, of fills that did not happen,
which `replay` does not return yet. Until it does, the honest output is
silence rather than a number pointing the way its own construction leans.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter

from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..engine import candles
from ..engine.candles import load_candles
from ..engine.runner import default_pip_size
from ..engine.structure import Direction
from .replay import replay


def _net_points(trades, pip: float, spread: float) -> list[tuple]:
    """(exit time, net R) per trade, spread charged against its own risk.

    Returned rather than just summed so several instruments' curves can be
    merged in exit order for a pooled drawdown. Ordered by EXIT, not
    entry: a trade that opens early and closes late belongs where its
    result actually landed, and sorting by entry draws a smoother curve
    than anyone lived.
    """
    out = []
    for t in trades:
        risk_pips = abs(t.entry - t.stop) / pip
        cost = (spread / risk_pips) if risk_pips else 0.0
        out.append(((t.exit_time or t.entry_time, t.entry_time),
                    t.r - cost, t.outcome))
    return sorted(out)


def _curve(points) -> tuple[float, int]:
    """Max drawdown and the longest run of non-winners, in one walk.

    R/trade alone cannot say whether a system is tradeable. 0.30 R/trade
    over 475 trades is ~140R a year, which at 0.5% risk is a very good
    year -- unless the path there includes a 40R hole, in which case that
    sizing is a 20% account drawdown and the annual figure is irrelevant
    because you would have stopped trading. So the drawdown leads.
    """
    peak = equity = max_dd = 0.0
    streak = worst = 0
    for _, net_r, outcome in points:
        equity += net_r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if outcome == "target":
            streak = 0
        else:
            streak += 1
            worst = max(worst, streak)
    return max_dd, worst


def _stats(trades, pip: float, spread: float) -> dict:
    """Totals for one bucket of trades. Spread is charged per trade."""
    n = len(trades)
    if not n:
        return {}
    wins = [t for t in trades if t.outcome == "target"]
    losses = [t for t in trades if t.outcome != "target"]
    gross = sum(t.r for t in trades)
    points = _net_points(trades, pip, spread)
    net = sum(p[1] for p in points)
    max_dd, worst_streak = _curve(points)
    won = sum(t.r for t in wins)
    lost = -sum(t.r for t in losses)
    return {
        "n": n,
        "win": 100.0 * len(wins) / n,
        "gross": gross,
        "gross_per": gross / n,
        "net": net,
        "net_per": net / n,
        "max_dd": max_dd,
        "worst_streak": worst_streak,
        "profit_factor": (won / lost) if lost else float("inf"),
        "avg_win": (won / len(wins)) if wins else 0.0,
        "avg_loss": (lost / len(losses)) if losses else 0.0,
        "ambiguous": sum(1 for t in trades if t.same_candle_stop),
        "points": points,
    }


def _line(label: str, s: dict) -> str:
    if not s:
        return f"  {label:<14} no trades"
    return (f"  {label:<14} {s['n']:>5}  win {s['win']:>5.1f}%  "
            f"net {s['net']:>+9.1f}R  {s['net_per']:>+6.2f}R/trade  "
            f"PF {s['profit_factor']:>5.2f}  maxDD {s['max_dd']:>7.1f}R  "
            f"streak {s['worst_streak']:>3}")


def _dump(trades, path: str):
    """Per-trade CSV, so a later question does not need another run.

    Written as soon as the instrument finishes rather than at the end, so
    a run that dies partway -- a closed terminal, an OOM -- still leaves
    everything it had already computed.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entry_time", "exit_time", "direction", "form",
                         "entry", "stop", "target", "exit", "outcome", "r",
                         "setup_price", "liquidity", "mitigation",
                         "same_candle_stop"])
        for t in trades:
            writer.writerow([t.entry_time, t.exit_time, t.direction.value,
                             t.form, t.entry, t.stop, t.target, t.exit,
                             t.outcome, t.r, t.setup_price, t.liquidity,
                             t.mitigation, int(t.same_candle_stop)])


def run_one(instrument: str, n: int, spread: float, source: str,
            dump_dir: str = "") -> list:
    """Load the four series and replay them. Missing series are fatal --
    a cascade that silently ran without its Weekly would produce a number
    nobody could interpret."""
    series = {}
    for code in ("W", "D", "H4", "H1"):
        try:
            series[code] = load_candles(source, instrument, code)
        except Exception as exc:                     # noqa: BLE001
            print(f"{instrument}: cannot load {code} -- {exc}", file=sys.stderr)
            return []
    if not series["H1"]:
        print(f"{instrument}: no H1 data", file=sys.stderr)
        return []

    trades = replay(series["W"], series["D"], series["H4"], series["H1"], n)

    pip = default_pip_size(instrument)
    span = f"{series['H1'][0].time.date()} to {series['H1'][-1].time.date()}"
    print(f"\n{instrument}  n={n}  spread={spread}p  "
          f"{len(series['H1'])} H1 bars  {span}")

    overall = _stats(trades, pip, spread)
    print(_line("ALL", overall))
    if overall:
        print(f"  {'':<14} ambiguous fills (filled then stopped, same bar): "
              f"{overall['ambiguous']}")

    by_form = Counter(t.form for t in trades)
    for form in sorted(by_form):
        print(_line(form, _stats([t for t in trades if t.form == form],
                                 pip, spread)))

    for side, name in ((Direction.BULLISH, "buys"), (Direction.BEARISH, "sells")):
        print(_line(name, _stats([t for t in trades if t.direction == side],
                                 pip, spread)))

    if dump_dir and trades:
        _dump(trades, os.path.join(dump_dir, f"{instrument}_slk_n{n}.csv"))

    # Each instrument is read once, so nothing here is wanted again. The
    # loader's cache never evicts, and 27 instruments of W/D/H4/H1 held at
    # once is over a gigabyte on a box that is already swapping.
    candles.clear_cache()
    return trades


def main():
    parser = argparse.ArgumentParser(
        description="Replay the SLK cascade on cached data.")
    parser.add_argument("--instrument", action="append", default=[],
                        help="Repeatable. Omit with --all.")
    parser.add_argument("--all", action="store_true",
                        help="Every instrument in instruments.py.")
    parser.add_argument("--n", type=int, required=True,
                        help="Swing width. REQUIRED -- the course gives no "
                             "number, so you have to choose one and say so.")
    parser.add_argument("--spread", type=float, default=0.0,
                        help="Spread in pips, charged per trade against that "
                             "trade's own risk. 0 reports gross only.")
    parser.add_argument("--source", default="dukascopy")
    parser.add_argument("--dump-trades", default="backtest/results/slk",
                        help="Per-trade CSVs, written as each instrument "
                             "finishes so a run that dies partway keeps what "
                             "it had. Empty string to skip.")
    args = parser.parse_args()

    targets = (sorted(DUKASCOPY_INSTRUMENTS) if args.all
               else args.instrument)
    if not targets:
        sys.exit("Pass --instrument SYMBOL (repeatable) or --all.")

    # Said once, because "100% win rate, negative net" looks like a bug
    # until you know PF is gross and net is not.
    print("net = after spread, charged per trade as spread/risk_pips.")
    print("PF  = GROSS profit factor, before that cost.")
    print("maxDD, streak = peak-to-trough of the NET curve in exit order.")

    # Kept per instrument, because pip size differs and a combined line
    # computed with one pip would misprice every JPY pair in the set.
    buckets = [(instrument, run_one(instrument, args.n, args.spread,
                                    args.source, args.dump_trades),
                default_pip_size(instrument)) for instrument in targets]

    pooled = _combine(buckets, args.spread)
    if len(targets) > 1:
        print("\nCOMBINED")
        print(_line("ALL", pooled))
        forms = {t.form for _, trades, _ in buckets for t in trades}
        for form in sorted(forms):
            print(_line(form, _combine(
                [(i, [t for t in trades if t.form == form], pip)
                 for i, trades, pip in buckets], args.spread)))
    _sizing(pooled)


def _sizing(s: dict):
    """What the drawdown means for position size.

    The only line in this report that answers "is this tradeable". A
    system's annual R is irrelevant if the path to it would have stopped
    you out of trading, so the hole gets translated into account terms.
    """
    if not s:
        return
    print()
    print(f"  avg win {s['avg_win']:+.2f}R   avg loss {-s['avg_loss']:+.2f}R"
          f"   longest run of non-winners {s['worst_streak']}")
    print("  WHAT THE DRAWDOWN MEANS FOR SIZING")
    for risk in (0.25, 0.5, 1.0):
        print(f"    at {risk}% risk/trade: the worst stretch is "
              f"{s['max_dd'] * risk:.1f}% of the account")
    print()
    print("  Pooled drawdown is walked over the MERGED curve in exit order,")
    print("  which assumes every instrument traded together at equal risk. It")
    print("  is NOT the sum of the per-instrument holes -- those happen at")
    print("  different times and partly offset.")
    print()
    print("  NOT modelled: slippage, and correlation entirely. The EUR pairs")
    print("  and the JPY pairs move together, so the real portfolio risk is")
    print("  worse than these numbers read.")


def _combine(buckets, spread: float) -> dict:
    """Sum across instruments, each costed with its own pip size."""
    parts = [_stats(trades, pip, spread) for _, trades, pip in buckets]
    parts = [p for p in parts if p]
    if not parts:
        return {}
    n = sum(p["n"] for p in parts)
    gross = sum(p["gross"] for p in parts)
    net = sum(p["net"] for p in parts)
    wins = sum(p["win"] * p["n"] / 100.0 for p in parts)
    # The pooled drawdown is walked over the MERGED curve, not summed
    # from the per-instrument figures. Those happen at different times and
    # partly offset, so adding them overstates the hole; merging them is
    # what "you traded these together at equal risk" actually means.
    merged = sorted(p for part in parts for p in part["points"])
    max_dd, worst_streak = _curve(merged)
    won = sum(p["avg_win"] * p["win"] * p["n"] / 100.0 for p in parts)
    lost = sum(p["avg_loss"] * (100.0 - p["win"]) * p["n"] / 100.0
               for p in parts)
    return {
        "n": n,
        "win": 100.0 * wins / n,
        "gross": gross,
        "gross_per": gross / n,
        "net": net,
        "net_per": net / n,
        "max_dd": max_dd,
        "worst_streak": worst_streak,
        "profit_factor": (won / lost) if lost else float("inf"),
        "avg_win": (won / wins) if wins else 0.0,
        "avg_loss": (lost / (n - wins)) if n > wins else 0.0,
        "ambiguous": sum(p["ambiguous"] for p in parts),
        "points": merged,
    }


if __name__ == "__main__":
    main()
