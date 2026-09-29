import time, pandas as pd
from backtest.engine.runner import run_backtest, _utc
from backtest.tools.slk_system import slk_kwargs
from backtest.tools.run_slk import _stats, _report, _closed

START = _utc(pd.Timestamp("2025-10-01"))
INSTRUMENTS = ["EURUSD", "GBPJPY", "GBPNZD"]
SPREAD = 1.5

ARMS = {
    "E taught triggers + single_candle liquidity": {"liquidity_mode": "single_candle"},
    "F E + trigger_priority (Bishop's best-first)": {"liquidity_mode": "single_candle", "trigger_priority": True},
}
for name, ov in ARMS.items():
    t0 = time.time()
    print(f"\n=== ARM: {name} ===", flush=True)
    all_closed = []
    for inst in INSTRUMENTS:
        recs = run_backtest(inst, "conservative", start_date=START, **slk_kwargs(**ov))
        _report(f"{inst:<8}", _stats(recs, SPREAD))
        all_closed.extend(_closed(recs))
    if all_closed:
        rs = [t.r_multiple for t in all_closed]
        wins = sum(1 for r in rs if r > 0); total = sum(rs)
        gw = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r <= 0)
        all_closed.sort(key=lambda t: t.exit_time)
        eq = peak = dd = 0.0; streak = worst = 0
        for t in all_closed:
            eq += t.r_multiple; peak = max(peak, eq); dd = max(dd, peak - eq)
            if t.r_multiple > 0: streak = 0
            else: streak += 1; worst = max(worst, streak)
        pf = gw/gl if gl else float('inf')
        print(f"  POOLED     n={len(rs):4d}  win={wins/len(rs)*100:5.1f}%  R/trade={total/len(rs):+.3f}  PF={pf:4.2f}  maxDD={dd:6.1f}R  worst-streak={worst}")
    print(f"  [{time.time()-t0:.0f}s]", flush=True)
