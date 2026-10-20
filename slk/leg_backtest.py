"""Can the bias be traded with a structural stop, and is a continuation break AFTER the target a tradable new leg?
(owner 2026-10-20, after the research reports: stopouts often reach the target later; after a target the next
target is touched ~73% of the time with no stop.)

Daily stories (slk.story.find_stories, code defaults). Every trade: entry at a closed candle's close, stop and
target fixed at entry, walked on H1 (stop first when one H1 candle touches both), closed at market after
MAX_DAYS. R = result / risk, minus COST_PIPS (spread + slippage) per trade.

Trades:
- "confirmation": entry at the D confirmation close, target = the story target (the bias trade of REPORT.md).
- "after target, 1st break": the first H4 continuation break (slk.live.continuation_breaks) after the story's
  target was hit and before the story line ends (slk.live.line_end); entry at that H4 close; target = the next
  target by the native rule (story._Ctx.target mode 'leg': next known origin ERL swing beyond every wick already
  seen since the confirmation, else the next fresh opposing key level) = the target ladder of
  research_bias_targets. "every break" = each such break (overlapping, not independent).
Stops: "tap wick" (story stop, confirmation only), "H4 swing N" = the highest high (sell) / lowest low (buy) of the
last N H4 candles up to the entry candle + 2 pips, "min M pips" = at least M pips wide.

    python -m slk.leg_backtest --start 2018 --end 2025 --out reports        # -> reports/LEG_REPORT.md
    python -m slk.leg_backtest --csv data/debug/GBPJPY_H1_ctrader.csv.gz      # one local file
"""
import argparse
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import instruments
from .candles import resample
from .live import CONT_DAYS, continuation_breaks, line_end
from .story import DEFAULT, _Ctx, find_stories

PAIRS = None  # set in main (slk.backtest.PAIRS)

COST_PIPS = 1.2   # 1 pip spread + 0.2 pip slippage, as the research reports
MAX_DAYS = 20     # = story max_hold (D bars)
BUFFER_PIPS = 2.0
STOPS = (("H4 swing 6", 6, 0), ("H4 swing 12", 12, 0), ("H4 swing 6, min 10 pips", 6, 10),
         ("H4 swing 12, min 15 pips", 12, 15))


def _naive(t):
    t = pd.Timestamp(t)
    return (t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t).to_datetime64()


def walk(H, t0, side, entry, stop, target, risk, cost):
    """H = dict of H1 arrays (t, high, low, close). Entry at time t0 (the signal candle's close)."""
    i = int(np.searchsorted(H["t"], t0, "left"))
    end = int(np.searchsorted(H["t"], t0 + np.timedelta64(MAX_DAYS, "D"), "left"))
    sell = side == "SELL"
    for k in range(i, min(end, len(H["t"]))):
        hs = H["high"][k] >= stop if sell else H["low"][k] <= stop
        ht = H["low"][k] <= target if sell else H["high"][k] >= target
        if hs:  # stop first, also when both are touched in one hour (conservative)
            ex, out = stop, "loss"
            if sell and H["open"][k] > stop or not sell and H["open"][k] < stop:
                ex = H["open"][k]  # gap through the stop
            break
        if ht:
            ex, out = target, "win"
            break
    else:
        k = min(end, len(H["t"])) - 1
        if k < i:
            return None
        ex, out = H["close"][k], "timeout"
    res = (entry - ex) if sell else (ex - entry)
    return {"outcome": out, "R": res / risk - cost / risk}


def swing_stop(C, k, side, n, pip, min_pips):
    lo = max(0, k - n + 1)
    if side == "SELL":
        s = float(C["high"][lo:k + 1].max()) + BUFFER_PIPS * pip
    else:
        s = float(C["low"][lo:k + 1].min()) - BUFFER_PIPS * pip
    return s, max(abs(s - C["close"][k]), min_pips * pip)


def pair_trades(pair, h1, cfg=None):
    cfg = {**DEFAULT, **(cfg or {})}
    pip = instruments.pip(pair)
    cost = COST_PIPS * pip
    stories = find_stories(pair, h1, "D", cfg)
    if not stories:
        return []
    X = _Ctx(pair, h1, "D", cfg)
    C = X.C
    c_end = np.array([_naive(t) for t in X.c_end])
    o_end = np.array([_naive(t) for t in X.o_end])
    idx = h1.index
    H = {"t": np.array([_naive(t) for t in idx]), **{k: h1[k].to_numpy(float) for k in ("open", "high", "low", "close")}}
    cb, ob = resample(h1, "H4"), resample(h1, "D")
    out = []

    def add(kind, stop_name, side, t0, entry, stop, risk, target, s):
        if risk <= 0 or target is None or ((target >= entry) if side == "SELL" else (target <= entry)):
            return
        w = walk(H, t0, side, entry, stop if stop_name == "tap wick" else
                 (entry + risk if side == "SELL" else entry - risk), target, risk, cost)
        if w:
            out.append({"pair": pair, "kind": kind, "stop_rule": stop_name, "side": side, "t": str(t0)[:16],
                        "risk_pips": round(risk / pip, 1), "target_pips": round(abs(target - entry) / pip, 1),
                        "story_tap": s["tap_time"], **w})

    for s in stories:
        side, sell = s["side"], s["side"] == "SELL"
        tc = _naive(s["confirm_time"])
        kc = int(np.searchsorted(c_end, tc, "right")) - 1  # last H4 closed at the confirmation
        if kc < 0:
            continue
        entry = float(C["close"][kc])
        if s.get("stop") is not None:
            add("confirmation", "tap wick", side, tc, entry, float(s["stop"]), abs(float(s["stop"]) - entry),
                s["target"], s)
        for name, n, mp in STOPS:
            st, risk = swing_stop(C, kc, side, n, pip, mp)
            add("confirmation", name, side, tc, entry, st, risk, s["target"], s)
        if s.get("kevin_outcome") != "target" or not s.get("end_time") or s.get("B") is None:
            continue
        r = {"side": side, "point_b": s["B"], "target": s["target"], "level": float(s["level"]),
             "breakout_time": pd.Timestamp(s["breakout_time"]).to_pydatetime(),
             "confirm_time": pd.Timestamp(s["confirm_time"]).to_pydatetime()}
        le = line_end(r, ob)
        cap = (pd.Timestamp(s["breakout_time"]) + pd.Timedelta(days=CONT_DAYS)).to_pydatetime()
        le = cap if le is None or pd.Timestamp(le) > pd.Timestamp(cap) else le  # as live: 60 days from the break
        te = _naive(s["end_time"])
        brks = [b for b in continuation_breaks(r, cb, cfg, le)
                if _naive(b["time"]) + np.timedelta64(4, "h") > te]
        for j, b in enumerate(brks):
            t0 = _naive(b["time"]) + np.timedelta64(4, "h")  # the H4 candle's close
            k = int(np.searchsorted(c_end, t0, "right")) - 1
            if k < 0:
                continue
            entry = float(C["close"][k])
            closed_o = int(np.searchsorted(o_end, t0, "right")) - 1
            seen = H["low"][(H["t"] >= tc) & (H["t"] < t0)]
            seen_hi = H["high"][(H["t"] >= tc) & (H["t"] < t0)]
            sw = (float(seen.min()) if sell else float(seen_hi.max())) if len(seen) else None
            tgt = X.target(sell, closed_o, X.c_end[k], entry, "leg", None, sw) if closed_o >= 0 else None
            for name, n, mp in STOPS:
                st, risk = swing_stop(C, k, side, n, pip, mp)
                for kind in (["after target, 1st break"] if j == 0 else []) + ["after target, every break"]:
                    add(kind, name, side, t0, entry, st, risk, tgt, s)
    return out


def table(df):
    rows = []
    for (kind, stop), d in df.groupby(["kind", "stop_rule"], sort=False):
        rows.append({"trades": kind, "stop": stop, "n": len(d), "win%": round((d["outcome"] == "win").mean() * 100, 1),
                     "stopped%": round((d["outcome"] == "loss").mean() * 100, 1),
                     "avg_R": round(d["R"].mean(), 3), "total_R": round(d["R"].sum(), 1),
                     "median risk pips": d["risk_pips"].median(), "median target pips": d["target_pips"].median()})
    return pd.DataFrame(rows)


def _job(args):
    pair, start, end = args
    from .backtest import _load
    h1 = _load(pair, start, end)
    return [] if h1 is None else pair_trades(pair, h1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2018)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--pairs", default="")
    ap.add_argument("--csv", default="", help="one local H1 csv(.gz) with t,open,high,low,close (pair from the name)")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    if a.csv:
        h1 = pd.read_csv(a.csv, parse_dates=["t"], index_col="t")
        rows = pair_trades(os.path.basename(a.csv).split("_")[0], h1)
    else:
        from .backtest import PAIRS as ALL
        pairs = [p.strip() for p in a.pairs.split(",") if p.strip()] or (ALL.split() if isinstance(ALL, str) else list(ALL))
        with ProcessPoolExecutor() as ex:
            rows = [r for rs in ex.map(_job, [(p, a.start, a.end) for p in pairs]) for r in rs]
    df = pd.DataFrame(rows)
    if df.empty:
        print("no trades")
        return 1
    t = table(df)
    by_year = df.assign(year=df["t"].str[:4]).query("stop_rule == 'H4 swing 12, min 15 pips'") \
        .groupby(["kind", "year"])["R"].agg(["count", "mean", "sum"]).round(3)
    txt = ("# Leg backtest (structural stops; continuation after the target)\n\n" + (__doc__ or "") +
           f"\n\nDaily stories, {df['pair'].nunique()} pairs. Cost {COST_PIPS} pips per trade.\n\n" +
           t.to_markdown(index=False) + "\n\n## By year (stop H4 swing 12, min 15 pips)\n\n" + by_year.to_markdown() + "\n")
    print(txt)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        open(os.path.join(a.out, "LEG_REPORT.md"), "w").write(txt)
        df.to_csv(os.path.join(a.out, "leg_trades.csv"), index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
