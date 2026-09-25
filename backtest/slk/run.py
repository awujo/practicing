"""
Run the replay on cached data and print what it did.

    python -m backtest.slk.run --instrument EURUSD --n 2
    python -m backtest.slk.run --all --n 2 --spread 1.0

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
import sys
from collections import Counter

from ..data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from ..engine.candles import load_candles
from ..engine.runner import default_pip_size
from ..engine.structure import Direction
from .replay import replay


def _stats(trades, pip: float, spread: float) -> dict:
    """Totals for one bucket of trades. Spread is charged per trade."""
    n = len(trades)
    if not n:
        return {}
    wins = [t for t in trades if t.outcome == "target"]
    gross = sum(t.r for t in trades)
    cost = 0.0
    for t in trades:
        risk_pips = abs(t.entry - t.stop) / pip
        if risk_pips:
            cost += spread / risk_pips
    return {
        "n": n,
        "win": 100.0 * len(wins) / n,
        "gross": gross,
        "gross_per": gross / n,
        "net": gross - cost,
        "net_per": (gross - cost) / n,
        "ambiguous": sum(1 for t in trades if t.same_candle_stop),
    }


def _line(label: str, s: dict) -> str:
    if not s:
        return f"  {label:<14} no trades"
    return (f"  {label:<14} {s['n']:>5}  win {s['win']:>5.1f}%  "
            f"gross {s['gross']:>+9.1f}R  {s['gross_per']:>+6.2f}R/trade  "
            f"net {s['net']:>+9.1f}R  {s['net_per']:>+6.2f}R/trade")


def run_one(instrument: str, n: int, spread: float, source: str) -> list:
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
    args = parser.parse_args()

    targets = (sorted(DUKASCOPY_INSTRUMENTS) if args.all
               else args.instrument)
    if not targets:
        sys.exit("Pass --instrument SYMBOL (repeatable) or --all.")

    # Kept per instrument, because pip size differs and a combined line
    # computed with one pip would misprice every JPY pair in the set.
    buckets = [(instrument, run_one(instrument, args.n, args.spread,
                                    args.source),
                default_pip_size(instrument)) for instrument in targets]

    if len(targets) > 1:
        print("\nCOMBINED")
        print(_line("ALL", _combine(buckets, args.spread)))
        forms = {t.form for _, trades, _ in buckets for t in trades}
        for form in sorted(forms):
            print(_line(form, _combine(
                [(i, [t for t in trades if t.form == form], pip)
                 for i, trades, pip in buckets], args.spread)))


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
    return {
        "n": n,
        "win": 100.0 * wins / n,
        "gross": gross,
        "gross_per": gross / n,
        "net": net,
        "net_per": net / n,
        "ambiguous": sum(p["ambiguous"] for p in parts),
    }


if __name__ == "__main__":
    main()
