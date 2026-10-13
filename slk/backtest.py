"""Backtest the story-line bias on history and write a report.

python -m slk.backtest --pairs EURUSD,GBPJPY --start 2018 --end 2025 --out reports
"""
import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from . import store
from .story import DEFAULT, apply_mw_filter, find_stories

PAIRS = ("EURUSD GBPUSD AUDUSD NZDUSD USDJPY USDCAD USDCHF EURGBP EURJPY EURAUD EURCAD EURCHF EURNZD "
         "GBPJPY GBPAUD GBPCAD GBPCHF GBPNZD AUDJPY AUDCAD AUDCHF AUDNZD NZDJPY NZDCAD NZDCHF CADJPY "
         "CADCHF CHFJPY").split()


def summarize(df, by):
    g = df.groupby(by)
    out = pd.DataFrame({
        "stories": g.size(),
        "win%": (g["outcome"].apply(lambda s: (s == "win").mean()) * 100).round(1),
        "avg_R_target": g["R"].mean().round(2),
        "expectancy_R": g["result_R"].mean().round(3),
        "total_R": g["result_R"].sum().round(1),
        "kevin_target%": (g["kevin_outcome"].apply(lambda s: (s == "target").mean()) * 100).round(1),
        "median_stop_pips": g["stop_pips"].median().round(1),
    })
    return out


def mw_section(df, cfg):
    """Report lines: D stories with and without the M/W conflict filter (STRATEGY §2 no-trade rule)."""
    d = df[df["story"] == "D"].copy()
    if d.empty:
        return []
    nt = d["no_trade"].astype(bool)
    views = [("all D stories (filter off)", d), ("tradable (filter on)", d[~nt]), ("NO_TRADE: M/W conflict", d[nt])]
    parts = [v.assign(view=name) for name, v in views if not v.empty]
    tab = summarize(pd.concat(parts), "view").reindex([n for n, v in views if not v.empty])
    state = "on" if cfg.get("mw_conflict_filter", True) else "off (no D story is marked)"
    return ["## M/W conflict filter (D story)", "",
            f"Filter is {state}. Tables above score tradable stories only; here all D stories vs the ones the",
            "filter keeps vs the ones it removes (latest confirmed M and W stories pointed opposite ways).", "",
            tab.to_markdown(), ""]


def pair_rows(pair, start, end, stories, cfg):
    """All story rows of one pair; D stories carry `no_trade` from the M/W filter (M and W are computed for it
    even when not requested, and then dropped)."""
    try:
        h1 = store.hourly(pair, start, end)
    except RuntimeError as e:  # no candles for this pair (download refused): skip it, keep the other pairs
        print(f"{pair}: skipped ({e})", flush=True)
        return []
    h1 = h1[(h1.index.year >= start) & (h1.index.year <= end)]
    need = list(stories) + ([s for s in ("W", "M") if s not in stories] if "D" in stories else [])
    found = {st: find_stories(pair, h1, st, cfg) for st in need}
    if "D" in found:
        found["D"] = apply_mw_filter(found["D"], found.get("M", []), found.get("W", []), cfg)
    out = []
    for st in stories:
        n_nt = sum(1 for r in found[st] if r.get("no_trade"))
        print(f"{pair} {st}: {len(found[st])} stories" + (f" ({n_nt} NO_TRADE M/W)" if st == "D" else ""), flush=True)
        out += found[st]
    return out


def _pair_job(args):
    return pair_rows(*args)


def run_pairs(fn, jobs, workers=None):
    """fn(job) for every job in a process pool (CPU-bound engine), results in job order."""
    workers = workers or int(os.environ.get("SLK_WORKERS", "0") or 0) or (os.cpu_count() or 1)
    if workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(min(workers, len(jobs))) as ex:
            return list(ex.map(fn, jobs))
    return [fn(j) for j in jobs]


def report(df, cfg, path):
    lines = ["# SLK story-line backtest", "",
             "Each row = a confirmed story (tap-reject-close + breakout of point B). Trade view: entry at the",
             "confirmation close, stop beyond the tap wick, target = nearest opposite level/swing.",
             "`win%` = target before stop. `expectancy_R` = average result in R (>0 = profitable before costs).",
             "`kevin_target%` = target reached before an origin close back through the level (Kevin's invalidation).", "",
             f"Settings: `{json.dumps(cfg)}`", ""]
    if df.empty:
        lines.append("No stories found.")
    else:
        df["no_trade"] = df["no_trade"].fillna(False).astype(bool) if "no_trade" in df else False
        allrows = df
        df = df[~df["no_trade"]].copy()  # D stories while M and W disagree are NO_TRADE: not scored
        df["year"] = df["tap_time"].str[:4]
        sections = [("By story", ["story"]), ("By story and side", ["story", "side"]),
                    ("By story and higher-TF agreement", ["story", "htf_agree"]),
                    ("By story and level type", ["story", "level_kind"]), ("By story and rule", ["story", "rule"]), ("By year (D story)", ["year"]),
                    ("By pair (D story)", ["pair"])]
        df["htf_agree"] = df.apply(lambda r: "agree" if (r["side"] == "BUY" and r.get("htf_trend") == "up") or
                                   (r["side"] == "SELL" and r.get("htf_trend") == "down") else
                                   "no HTF" if pd.isna(r.get("htf_trend")) else "not agree", axis=1)
        for title, by in sections:
            d = df[df["story"] == "D"] if "D story" in title else df
            if d.empty:
                continue
            lines += [f"## {title}", "", summarize(d, by).to_markdown(), ""]
        lines += mw_section(allrows, cfg)
    open(path, "w").write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=",".join(PAIRS))
    ap.add_argument("--start", type=int, default=2018)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--stories", default="D,W,M")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--cfg", default="{}", help="JSON overrides of story.DEFAULT")
    a = ap.parse_args()
    cfg = {**DEFAULT, **json.loads(a.cfg)}
    os.makedirs(a.out, exist_ok=True)
    pairs, stories = a.pairs.split(","), a.stories.split(",")
    store.months_all(pairs, a.start, a.end)  # candle store: only missing month files are downloaded
    rows = [r for chunk in run_pairs(_pair_job, [(p, a.start, a.end, stories, cfg) for p in pairs]) for r in chunk]
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(a.out, "stories.csv"), index=False)
    report(df, cfg, os.path.join(a.out, "REPORT.md"))
    print(open(os.path.join(a.out, "REPORT.md")).read())


if __name__ == "__main__":
    main()
