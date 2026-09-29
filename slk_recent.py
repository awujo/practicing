"""Recent-window SLK run: last year + this year (2025-10-01 onward).

Wraps backtest.tools.run_slk's reporting but passes start_date so the
focus is the regime human traders are currently trading. Also A/Bs the
teaching-aligned options one at a time, per the repo's own rule that
nothing joins the baseline without a number showing it helps.
"""
import sys, time
from backtest.engine.runner import run_backtest, TRIGGERS_TAUGHT
from backtest.tools.slk_system import slk_kwargs
from backtest.tools.run_slk import _stats, _report, _closed
import pandas as pd

from backtest.engine.runner import _utc
START = _utc(pd.Timestamp("2025-10-01"))
INSTRUMENTS = ["EURUSD", "GBPJPY", "GBPNZD"]
SPREAD = 1.5

ARMS = {
    "A baseline (taught triggers)": {},
    "B + trigger_priority": {"trigger_priority": True},
    "C + limit fill (SLK_SPEC 5.1/5.2 return-to-level)": {"entry_fill": "limit"},
    "D both B+C": {"trigger_priority": True, "entry_fill": "limit"},
}

def run(overrides):
    out = {}
    for inst in INSTRUMENTS:
        kwargs = slk_kwargs(**overrides)
        recs = run_backtest(inst, "conservative", start_date=START, **kwargs)
        out[inst] = recs
    return out

for name, ov in ARMS.items():
    t0 = time.time()
    print(f"\n=== ARM: {name} ===", flush=True)
    all_closed = []
    for inst, recs in run(ov).items():
        s = _stats(recs, SPREAD)
        _report(f"{inst:<8}", s)
        all_closed.extend(_closed(recs))
    if all_closed:
        import statistics as st
        rs = [t.r_multiple for t in all_closed if getattr(t, "r_multiple", None) is not None]
        wins = sum(1 for r in rs if r > 0)
        total = sum(rs)
        gross_w = sum(r for r in rs if r > 0); gross_l = -sum(r for r in rs if r <= 0)
        # equity curve on exit order
        all_closed.sort(key=lambda t: t.exit_time)
        eq = 0.0; peak = 0.0; dd = 0.0
        streak = 0; worst_streak = 0
        for t in all_closed:
            eq += t.r_multiple
            peak = max(peak, eq); dd = max(dd, peak - eq)
            if t.r_multiple > 0: streak = 0
            else:
                streak += 1; worst_streak = max(worst_streak, streak)
        pf = gross_w / gross_l if gross_l else float("inf")
        print(f"  POOLED     n={len(rs):4d}  win={wins/len(rs)*100:5.1f}%  "
              f"R/trade={total/len(rs):+.3f}  PF={pf:4.2f}  maxDD={dd:6.1f}R  "
              f"worst-streak={worst_streak}")
    print(f"  [{time.time()-t0:.0f}s]", flush=True)
