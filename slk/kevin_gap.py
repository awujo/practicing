"""Study 2 (research/TREND_LTF_PLAN.md): why does the bot not see Kevin's own trades (tests/kevin_trades.json)?

For each trade, around Kevin's time (WINDOW_DAYS either side):
  1. D / W story state on his side (slk.trend_study.daily_state): is there a bias he is trading with?
  2. H4 stories on his side (tap -> H1 break of B) confirmed in the window; level distance to his entry.
  3. Kevin continuation levels (slk.trend_study.pattern_trades, H4/H2/H1, limit at the line) on his side filled in
     the window; the closest line to his entry, its stop vs his stop.
  4. If no H4 story is found: re-run the H4 and D stories with ONE filter off at a time and name the filters
     that make a story on his side appear in the window.
Report: reports/KEVIN_GAP.md.

    python -m slk.kevin_gap --data data/examples --out reports
"""
import argparse
import os

import numpy as np
import pandas as pd

from . import instruments
from .story import DEFAULT, find_stories
from .trend_study import _naive, daily_state, pattern_trades
from .verify_trades import load_trades

WINDOW_DAYS = 3
TOGGLES = {"trend_filter": False, "htf_filter": False, "next_day_rule": "off", "target_unswept": False,
           "same_bar_close": False, "align_retap_ends": False, "flip_end": False, "max_wait": 10,
           "pullback_levels": False, "flip_max_age": 0}


def _near(rows, side, t, key):
    lo, hi = t - np.timedelta64(WINDOW_DAYS, "D"), t + np.timedelta64(WINDOW_DAYS, "D")
    return [r for r in rows if r["side"] == side and r.get(key) and lo <= _naive(r[key]) <= hi]


def check(trade, h1, pats=None):
    pair, side = trade["pair"], trade["side"]
    pip = instruments.pip(pair)
    t = _naive(trade["time"])
    e, s = float(trade["entry"]), float(trade["stop"])
    out = {"id": trade["id"], "kevin": f"{trade['tf']} {side} {trade['time']} entry {e} stop {s} ({trade['stop_pips']} p)"}
    d_st, w_st = find_stories(pair, h1, "D", DEFAULT), find_stories(pair, h1, "W", DEFAULT)
    out["D story"], out["W story"] = daily_state(d_st, side, t), daily_state(w_st, side, t)
    h4 = _near(find_stories(pair, h1, "H4", DEFAULT), side, t, "confirm_time")
    if h4:
        b = min(h4, key=lambda r: abs(float(r["level"]) - e))
        out["H4 story"] = (f"{len(h4)} found; closest level {float(b['level']):.5g} ({abs(float(b['level']) - e) / pip:.1f} p "
                           f"from his entry), confirmed {b['confirm_time']}, stop {float(b['stop']):.5g}, {b['kevin_outcome']}")
    else:
        out["H4 story"] = "none"
    pats = pattern_trades(pair, h1) if pats is None else pats
    lo, hi = t - np.timedelta64(WINDOW_DAYS, "D"), t + np.timedelta64(WINDOW_DAYS, "D")
    near = [p for p in pats if p["side"] == side and p["entry"] == "limit" and lo <= _naive(p["t"]) <= hi]
    if near:
        b = min(near, key=lambda p: abs(p["entry_price"] - e))
        out["levels"] = (f"{len(near)} filled; closest {b['tf']} line {b['entry_price']:.5g} "
                         f"({abs(b['entry_price'] - e) / pip:.1f} p from his entry) stop {b['stop_price']:.5g} "
                         f"({b['stop_pips']} p) at {b['t']}, 2R {'won' if b['win_2R'] else 'lost'}")
    else:
        out["levels"] = "none"
    blockers = []
    if not h4:
        base_d = _near(d_st, side, t, "confirm_time")
        for k, v in TOGGLES.items():
            for st in ("H4",) + (() if base_d else ("D",)):
                got = _near(find_stories(pair, h1, st, {**DEFAULT, k: v}), side, t, "confirm_time")
                if got:
                    blockers.append(f"{st}: {k}={v}")
    out["appears when"] = ", ".join(blockers) if blockers else ("-" if h4 else "no single filter")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/examples")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    rows = []
    for tr in load_trades():
        f = os.path.join(a.data, f"{tr['pair']}_H1.csv.gz")
        if not os.path.exists(f):
            rows.append({"id": tr["id"], "kevin": "no data"})
            continue
        h1 = pd.read_csv(f, parse_dates=["t"], index_col="t")
        rows.append(check(tr, h1))
    txt = ("# Why the bot misses Kevin's trades\n\n" + (__doc__ or "") + "\n\n" +
           pd.DataFrame(rows).to_markdown(index=False) + "\n")
    print(txt)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        open(os.path.join(a.out, "KEVIN_GAP.md"), "w").write(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
