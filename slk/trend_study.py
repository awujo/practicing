"""Study 1 (research/TREND_LTF_PLAN.md): trend entries on H4 key levels, the way Kevin trades.

Owner 2026-10-20. Replaying Kevin's trades showed he trades WITH the D/W trend on H4/H2/H1 key levels with
7-19 pip stops, often after the Daily story already hit its target. Here: every H4 story (slk.story, STORIES H4 =
H4 key-level tap-reject-close + H1 body close beyond point B, same rules as the D story), whatever the Daily
story is doing.

Trade: entry at the H1 confirmation close, stop = the story stop (tap candle wick + 2 pips), walked on H1 for
MAX_DAYS (stop first when one H1 candle touches stop and target), COST_PIPS per trade. One row per story with the
path outcome for every target at once: +1R / +2R / +3R / +5R / the story target (the H4 ERL), MFE (best R
before the stop) and the lower-TF features of slk.ltf_features. Filters are columns, applied in the report:
  trend: none / D agrees / D and W agree (structure trend of the last CLOSED D / W candle at the entry)
  stop: tap wick / at least 7 pips (Kevin's smallest) / skip when wider than 25 pips (Kevin "15 to 20 pips")
  daily: D story on the same side active / D target already hit / no D story

    python -m slk.trend_study --data data/examples --out reports/trend_local      # local 8 pairs
    python -m slk.trend_study --start 2018 --end 2025 --out reports               # Actions, 28 pairs
"""
import argparse
import glob
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import instruments
from .candles import resample
from .ltf_features import H1Trend, features
from . import entry as E
from .story import DEFAULT, _structure, find_stories
from .structure import SwingBook, trend

COST_PIPS = 1.2
MAX_DAYS = 5
LEVELS = (1, 2, 3, 5)
MIN_STOP = 7.0
MAX_STOP = 25.0


def _naive(t):
    t = pd.Timestamp(t)
    return (t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t).to_datetime64()


class _TF:
    """Trend of a TF at a time t, from the candles CLOSED at t."""

    def __init__(self, h1, tf, cfg):
        ob = resample(h1, tf)
        self.end = np.array([_naive(x) for x in ob["end"]])
        self.close = ob["close"].to_numpy(float)
        self.high, self.low = ob["high"].to_numpy(float), ob["low"].to_numpy(float)
        self.sb = SwingBook(_structure(ob, cfg, tf))

    def last(self, t):
        return int(np.searchsorted(self.end, t, "right")) - 1

    def trend(self, t):
        i = self.last(t)
        return trend(self.sb.at(i), float(self.close[i])) if i >= 2 else "range"


def path(H, k, side, entry, stop, target, pip):
    """Outcome of one trade entered at the close of H1 candle k. Returns dict of R results per target rule."""
    sell = side == "SELL"
    risk = abs(entry - stop)
    cost = COST_PIPS * pip / risk
    end = int(np.searchsorted(H["t"], H["t"][k] + np.timedelta64(MAX_DAYS, "D"), "left"))
    goals = {f"{n}R": (entry - n * risk) if sell else (entry + n * risk) for n in LEVELS}
    if target is not None and ((target < entry) if sell else (target > entry)):
        goals["target"] = target
    hit, mfe, stop_k = {}, 0.0, None
    for j in range(k + 1, min(end, len(H["t"]))):
        if (H["high"][j] >= stop) if sell else (H["low"][j] <= stop):
            stop_k = j
            break
        best = (entry - H["low"][j]) if sell else (H["high"][j] - entry)
        mfe = max(mfe, best / risk)
        for g, p in goals.items():
            if g not in hit and ((H["low"][j] <= p) if sell else (H["high"][j] >= p)):
                hit[g] = j
    last = stop_k if stop_k is not None else min(end, len(H["t"])) - 1
    if last <= k:
        return None
    gap = 0.0
    if stop_k is not None:  # gap through the stop
        o = H["open"][stop_k]
        gap = max(0.0, (o - stop) if sell else (stop - o)) / risk
    close_R = ((entry - H["close"][last]) if sell else (H["close"][last] - entry)) / risk
    out = {"mfe_R": round(mfe, 2), "stopped": stop_k is not None,
           "hours_held": int(last - k)}
    for g, p in goals.items():
        r_win = abs(p - entry) / risk
        out[f"R_{g}"] = round((r_win if g in hit else (-1.0 - gap) if stop_k is not None else close_R) - cost, 3)
        out[f"win_{g}"] = g in hit
    if "target" not in goals:
        out["R_target"], out["win_target"] = np.nan, False
    return out


def daily_state(d_stories, side, t):
    """Latest D story confirmed before t: 'same' (active, target not hit yet), 'same_target_hit', 'opposite',
    'none'."""
    best = None
    for s in d_stories:
        c = _naive(s["confirm_time"])
        if c <= t and (best is None or c > _naive(best["confirm_time"])):
            best = s
    if best is None:
        return "none"
    if best["side"] != side:
        return "opposite"
    e = best.get("end_time")
    if e and _naive(e) <= t:
        return "same_target_hit" if best.get("kevin_outcome") == "target" else "same_ended"
    return "same"


def pair_trades(pair, h1, cfg=None):
    cfg = {**DEFAULT, **(cfg or {})}
    pip = instruments.pip(pair)
    stories = find_stories(pair, h1, "H4", cfg)
    if not stories:
        return []
    d_stories = find_stories(pair, h1, "D", cfg)
    H = {"t": np.array([_naive(t) for t in h1.index]),
         **{c: h1[c].to_numpy(float) for c in ("open", "high", "low", "close")}}
    D, W = _TF(h1, "D", cfg), _TF(h1, "W", cfg)
    ht = H1Trend(H)
    out = []
    for s in stories:
        side, sell = s["side"], s["side"] == "SELL"
        t_conf = _naive(s["confirm_time"])  # close of the H1 confirmation candle
        k = int(np.searchsorted(H["t"], t_conf - np.timedelta64(1, "h"), "left"))
        if k >= len(H["t"]) or H["t"][k] != t_conf - np.timedelta64(1, "h"):
            continue
        entry, stop = float(H["close"][k]), float(s["stop"])
        if (stop <= entry) if sell else (stop >= entry):
            continue
        p = path(H, k, side, entry, stop, s.get("target"), pip)
        if p is None:
            continue
        tap0 = int(np.searchsorted(H["t"], _naive(s["tap_time"]), "left"))
        di = D.last(t_conf)
        want = "down" if sell else "up"
        dt, wt = D.trend(t_conf), W.trend(t_conf)
        f = features(H, k, side, entry, stop, tap0, pip, ht,
                     (D.high[di], D.low[di]) if di >= 0 else None)
        out.append({"pair": pair, "side": side, "t": str(t_conf)[:16], "year": int(str(t_conf)[:4]),
                    "level_src": s.get("level_src") or "-", "break_kind": s.get("break_kind"), "rule": s.get("rule"),
                    "story_R": round(float(s["R"]), 2) if s.get("R") is not None else None,
                    "d_trend_agrees": dt == want, "w_trend_agrees": wt == want,
                    "h4_trend_agrees": s.get("trend") == want,
                    "daily": daily_state(d_stories, side, t_conf), **f, **p})
    return out


RETEST_BARS = 12  # entry-TF bars to wait for the retest of the line (entry.DEFAULT retest_bars)
PATTERN_TFS = ("H4", "H2", "H1")


def path_limit(H, f, side, entry, stop, target, pip):
    """Like path() for a limit order filled inside H1 candle f: the fill candle can only stop out (its high/low
    order is unknown), targets count from the next candle."""
    sell = side == "SELL"
    if (H["high"][f] >= stop) if sell else (H["low"][f] <= stop):
        risk = abs(entry - stop)
        r = {"mfe_R": 0.0, "stopped": True, "hours_held": 0}
        for n in LEVELS:
            r[f"R_{n}R"], r[f"win_{n}R"] = round(-1.0 - COST_PIPS * pip / risk, 3), False
        r["R_target"], r["win_target"] = (round(-1.0 - COST_PIPS * pip / risk, 3) if target is not None else np.nan), False
        return r
    return path(H, f, side, entry, stop, target, pip)


def pattern_trades(pair, h1, cfg=None, ecfg=None):
    """Every Kevin continuation level (entry.patterns: A/V-shape, 3rd-candle wick rejection, impulsive internal
    break) on H4 / H2 / H1, SELL and BUY, whatever the stories say. Limit at the line once the breakout candle has
    closed, valid RETEST_BARS entry-TF candles; Kevin's stop (zone, else rejection wick, max 20 pips); one row per
    filled level with the context at the breakout close: D / W trend, last H4 / D / W structural break, D and H4
    story state. No story is required: the report filters on the context."""
    cfg = {**DEFAULT, **(cfg or {})}
    ecfg = {**E.DEFAULT, "entry_tfs": E.ENTRY_TFS, **(ecfg or {}), "story_cfg": cfg}
    pip = instruments.pip(pair)
    px = E._Pair(pair, h1, ecfg)
    H = {"t": np.array([_naive(t) for t in h1.index]),
         **{c: h1[c].to_numpy(float) for c in ("open", "high", "low", "close")}}
    D, W = _TF(h1, "D", cfg), _TF(h1, "W", cfg)
    d_st, h4_st = find_stories(pair, h1, "D", cfg), find_stories(pair, h1, "H4", cfg)
    ht = H1Trend(H)
    out = []
    for tf in PATTERN_TFS:
        B = px.bars(tf)
        for sell in (True, False):
            side, want = ("SELL", "down") if sell else ("BUY", "up")
            for p in px.pats(tf, sell):
                bo = p["bo"]
                if bo + 1 >= len(B["end"]):
                    continue
                t0 = B["end"][bo]
                stop, at = E._stop(p, sell, ecfg, px.P)
                line = p["line"]
                risk = abs(stop - line)
                if risk <= 0 or risk / pip > ecfg["max_stop_pips"] + 1e-9:
                    continue
                exp = B["end"][min(bo + RETEST_BARS, len(B["end"]) - 1)]
                a = int(np.searchsorted(H["t"], t0, "left"))
                b = int(np.searchsorted(H["t"], exp, "left"))
                hit = np.flatnonzero(H["high"][a:b] >= line if sell else H["low"][a:b] <= line)
                if not len(hit):
                    continue
                f = a + int(hit[0])
                # target for the "target" column: the story target of the H4 story in line, if any
                h4s = daily_state(h4_st, side, t0)
                tgt = None
                for s in h4_st:
                    if s["side"] == side and _naive(s["confirm_time"]) <= t0 and (not s.get("end_time") or _naive(s["end_time"]) > t0):
                        tgt = s.get("target")
                # the two entries: "limit" = Kevin's limit at the line; "h1_confirm" = wait for an H1 candle that
                # (after the touch, the stop never reached) CLOSES back on the trade side of the line and enter at
                # that close, same stop (owner 2026-10-20 lower-TF confirmation idea; OUR CHOICE, not Kevin's rule)
                conf = None
                for j in range(f, b):
                    if (H["high"][j] >= stop) if sell else (H["low"][j] <= stop):
                        break
                    if (H["close"][j] < line) if sell else (H["close"][j] > line):
                        conf = j
                        break
                entries = [("limit", f, line, path_limit(H, f, side, line, stop, tgt, pip))]
                if conf is not None:
                    entries.append(("h1_confirm", conf, float(H["close"][conf]),
                                    path(H, conf, side, float(H["close"][conf]), stop, tgt, pip)))
                c1_h1 = int(np.searchsorted(H["t"], B["start"][p["c1"]], "left"))
                di = D.last(t0)
                for kind, kf, ent, pth in entries:
                    if pth is None:
                        continue
                    kx = max(kf - 1, 0) if kind == "limit" else kf  # features from candles closed at the entry
                    ft = features(H, kx, side, ent, stop, c1_h1, pip, ht,
                                  (D.high[di], D.low[di]) if di >= 0 else None)
                    out.append({**_row(pair, tf, side, H, kf, kind, at, p, bo, B, a, D, W, px, t0, want, d_st, h4s, ft, pth),
                                "entry_price": round(ent, 6), "stop_price": round(stop, 6)})
    return out


def _row(pair, tf, side, H, kf, kind, at, p, bo, B, a, D, W, px, t0, want, d_st, h4s, ft, pth):
    """One pattern_trades row."""
    body = abs(B["close"][bo] - B["open"][bo])
    bodies = np.abs(B["close"][max(0, bo - 10):bo] - B["open"][max(0, bo - 10):bo])
    return {"pair": pair, "tf": tf, "entry": kind, "side": side, "t": str(H["t"][kf])[:16],
            "year": int(str(H["t"][kf])[:4]), "stop_at": at, "bo_candle": bo - p["c1"] + 1,
            "bo_body_x_avg": round(float(body / bodies.mean()), 2) if len(bodies) and bodies.mean() > 0 else np.nan,
            "hours_to_fill": int(kf - a),
            "d_trend_agrees": D.trend(t0) == want, "w_trend_agrees": W.trend(t0) == want,
            "h4_break_agrees": px.last_break("H4", t0) == want,
            "d_break_agrees": px.last_break("D", t0) == want,
            "w_break_agrees": px.last_break("W", t0) == want,
            "daily": daily_state(d_st, side, t0), "h4_story": h4s, **ft, **pth}


def _filters(df):
    return {
        "all H4 stories": df,
        "D trend agrees": df[df["d_trend_agrees"]],
        "D + W trend agree": df[df["d_trend_agrees"] & df["w_trend_agrees"]],
        "D + W agree, stop <= 25 pips": df[df["d_trend_agrees"] & df["w_trend_agrees"] & (df["stop_pips"] <= MAX_STOP)],
        "D + W agree, D target already hit": df[df["d_trend_agrees"] & df["w_trend_agrees"] & (df["daily"] == "same_target_hit")],
        "D + W agree, D story same side active": df[df["d_trend_agrees"] & df["w_trend_agrees"] & (df["daily"] == "same")],
        "D + W agree, no D story / ended": df[df["d_trend_agrees"] & df["w_trend_agrees"] & df["daily"].isin(["none", "same_ended"])],
        "against D trend": df[~df["d_trend_agrees"]],
    }


def table(df):
    rows = []
    for name, d in _filters(df).items():
        if not len(d):
            continue
        r = {"filter": name, "n": len(d), "median stop pips": d["stop_pips"].median(), "MFE median R": d["mfe_R"].median()}
        for g in ("1R", "2R", "3R", "5R", "target"):
            r[f"{g} win%"] = round(d[f"win_{g}"].mean() * 100, 1)
            r[f"{g} avg R"] = round(d[f"R_{g}"].mean(), 3)
        rows.append(r)
    return pd.DataFrame(rows)


def _min_stop(df):
    """Same trades with the stop widened to MIN_STOP pips: re-run is needed for exact paths, so this is reported by
    the --min-stop run (cfg stop) only. Kept as a note."""
    return df


def _load_local(path):
    out = {}
    for f in sorted(glob.glob(os.path.join(path, "*_H1*.csv.gz"))):
        out[os.path.basename(f).split("_")[0]] = f
    return out


def _job(args):
    pair, src, start, end = args
    if src:
        h1 = pd.read_csv(src, parse_dates=["t"], index_col="t")
    else:
        from .backtest import _load
        h1 = _load(pair, start, end)
    if h1 is None:
        return []
    return pair_trades(pair, h1), pattern_trades(pair, h1)


def report(df, split):
    tr, te = df[df["year"] < split], df[df["year"] >= split]
    txt = ("# Trend entries on H4 key levels\n\n" + (__doc__ or "") +
           f"\n\n{df['pair'].nunique()} pairs, {df['t'].min()} .. {df['t'].max()}. Cost {COST_PIPS} pips. "
           f"Max hold {MAX_DAYS} days. avg R includes the cost; timeouts closed at market.\n\n"
           "## All years\n\n" + table(df).to_markdown(index=False) +
           f"\n\n## Before {split} (train)\n\n" + table(tr).to_markdown(index=False) +
           f"\n\n## {split} and later (test)\n\n" + table(te).to_markdown(index=False) + "\n")
    by = df[df["d_trend_agrees"] & df["w_trend_agrees"]].groupby("year")[["R_2R", "R_3R", "R_target"]].agg(["count", "mean"]).round(3)
    txt += "\n## By year (D + W agree)\n\n" + by.to_markdown() + "\n"
    return txt


def _pfilters(df):
    tr = df["d_trend_agrees"] & df["w_trend_agrees"]
    al = df["d_break_agrees"] & df["h4_break_agrees"]
    return {
        "all levels": df,
        "D + W trend agree": df[tr],
        "against the D trend": df[~df["d_trend_agrees"]],
        "D + H4 last break agree (Kevin: D and H4 in line)": df[al],
        "W + D + H4 last break agree": df[al & df["w_break_agrees"]],
        "D + W trend + D/H4 in line": df[tr & al],
        "D + W trend + D/H4 in line, D target already hit": df[tr & al & (df["daily"] == "same_target_hit")],
        "D + W trend + D/H4 in line, D story same side active": df[tr & al & (df["daily"] == "same")],
        "D + W trend + D/H4 in line, no D story": df[tr & al & df["daily"].isin(["none", "same_ended", "opposite"])],
        "D + W trend + D/H4 in line, inside an H4 story": df[tr & al & (df["h4_story"] == "same")],
    }


def _ptable(df):
    rows = []
    for name, d in _pfilters(df).items():
        if not len(d):
            continue
        r = {"filter": name, "n": len(d), "median stop pips": d["stop_pips"].median(), "MFE median R": d["mfe_R"].median()}
        for g in ("1R", "2R", "3R", "5R"):
            r[f"{g} win%"] = round(d[f"win_{g}"].mean() * 100, 1)
            r[f"{g} avg R"] = round(d[f"R_{g}"].mean(), 3)
        rows.append(r)
    return pd.DataFrame(rows)


def pattern_report(pt, split):
    if pt.empty:
        return "\n# Kevin continuation levels on H4/H2/H1\n\nno trades\n"
    txt = ("\n# Kevin continuation levels on H4 / H2 / H1 (limit at the line, Kevin's stop)\n\n" +
           (pattern_trades.__doc__ or "") + "\n")
    for tf, kind in [(t, k) for t in PATTERN_TFS for k in ("limit", "h1_confirm")]:
        d = pt[(pt["tf"] == tf) & (pt["entry"] == kind)]
        if not len(d):
            continue
        tf = f"{tf} {kind}"
        txt += (f"\n## {tf} levels: all years\n\n" + _ptable(d).to_markdown(index=False) +
                f"\n\n## {tf} levels: before {split} (train)\n\n" + _ptable(d[d["year"] < split]).to_markdown(index=False) +
                f"\n\n## {tf} levels: {split} and later (test)\n\n" + _ptable(d[d["year"] >= split]).to_markdown(index=False) + "\n")
    return txt


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2018)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--pairs", default="")
    ap.add_argument("--data", default="", help="folder of local H1 csv.gz files (PAIR_H1*.csv.gz)")
    ap.add_argument("--split", type=int, default=0, help="first test year (default: 2023, local data: 2025)")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    if a.data:
        files = _load_local(a.data)
        jobs = [(p, f, a.start, a.end) for p, f in files.items()]
    else:
        from .backtest import PAIRS as ALL
        pairs = [p.strip() for p in a.pairs.split(",") if p.strip()] or (ALL.split() if isinstance(ALL, str) else list(ALL))
        jobs = [(p, None, a.start, a.end) for p in pairs]
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(_job, jobs))
    df = pd.DataFrame([r for rs in res if rs for r in rs[0]])
    pt = pd.DataFrame([r for rs in res if rs for r in rs[1]])
    if df.empty:
        print("no trades")
        return 1
    split = a.split or (2025 if a.data else 2023)
    txt = report(df, split) + pattern_report(pt, split)
    print(txt)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        open(os.path.join(a.out, "TREND_REPORT.md"), "w").write(txt)
        df.to_csv(os.path.join(a.out, "trend_trades.csv.gz"), index=False)
        pt.to_csv(os.path.join(a.out, "pattern_trades.csv.gz"), index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
