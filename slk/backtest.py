"""Backtest the story-line bias on history and write a report.

python -m slk.backtest --pairs EURUSD,GBPJPY --start 2018 --end 2025 --out reports
"""
import argparse
import json
import os

import pandas as pd

from .data import hourly
from .story import DEFAULT, find_stories

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
        df["year"] = df["tap_time"].str[:4]
        sections = [("By story", ["story"]), ("By story and side", ["story", "side"]),
                    ("By story and higher-TF agreement", ["story", "htf_agree"]),
                    ("By story and level type", ["story", "level_kind"]), ("By year (D story)", ["year"]),
                    ("By pair (D story)", ["pair"])]
        df["htf_agree"] = df.apply(lambda r: "agree" if (r["side"] == "BUY" and r.get("htf_trend") == "up") or
                                   (r["side"] == "SELL" and r.get("htf_trend") == "down") else
                                   "no HTF" if pd.isna(r.get("htf_trend")) else "not agree", axis=1)
        for title, by in sections:
            d = df[df["story"] == "D"] if "D story" in title else df
            lines += [f"## {title}", "", summarize(d, by).to_markdown(), ""]
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
    rows = []
    for pair in a.pairs.split(","):
        h1 = hourly(pair, a.start, a.end)
        h1 = h1[(h1.index.year >= a.start) & (h1.index.year <= a.end)]
        for st in a.stories.split(","):
            r = find_stories(pair, h1, st, cfg)
            print(f"{pair} {st}: {len(r)} stories", flush=True)
            rows += r
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(a.out, "stories.csv"), index=False)
    report(df, cfg, os.path.join(a.out, "REPORT.md"))
    print(open(os.path.join(a.out, "REPORT.md")).read())


if __name__ == "__main__":
    main()
