"""Backtest the entry model (stage 2) on every confirmed story and write reports/ENTRY_REPORT.md.

python -m slk.entry_backtest --pairs EURUSD,GBPJPY --start 2018 --end 2025 --out reports
"""
import argparse
import json
import os

import pandas as pd

from .backtest import PAIRS
from .data import hourly
from .entry import DEFAULT, ENTRY_TFS, find_entries
from .story import DEFAULT as STORY_DEFAULT, find_stories


def summarize(df, by):
    g = df.groupby(by)
    trig = df[df["status"] == "TRIGGERED"]
    t = trig.groupby(by)
    out = pd.DataFrame({
        "stories": g.size(),
        "setups": g["status"].apply(lambda s: s.isin(["TRIGGERED", "MISSED", "PENDING"]).sum()),
        "filled": t.size(),
        "missed": g["status"].apply(lambda s: (s == "MISSED").sum()),
    }).fillna(0)
    out["fill%"] = (out["filled"] / out["setups"].where(out["setups"] > 0) * 100).round(1)
    for v in ("tp1", "tp2"):
        out[f"{v}_win%"] = (t[f"{v}_outcome"].apply(lambda s: (s == "win").mean()) * 100).round(1)
        out[f"{v}_avgR_target"] = t[f"R_{v}"].mean().round(2)
        out[f"{v}_expR"] = t[f"{v}_R"].mean().round(3)
        out[f"{v}_totalR"] = t[f"{v}_R"].sum().round(1)
    out["median_stop_pips"] = t["stop_pips"].median().round(1)
    out[["setups", "filled", "missed"]] = out[["setups", "filled", "missed"]].fillna(0).astype(int)
    return out


def report(df, cfg, path):
    lines = ["# SLK entry-model backtest", "",
             "Each row = a CONFIRMED story (see REPORT.md). On the entry TF (D story: H4 > H2 > H1; W: D > H4;",
             "M: W > D) the bot looks for the 4-candle continuation after the external breakout: c1-c2 A/V line,",
             "c3 wick rejection, c4 impulsive close beyond c1..c3; limit at the line, stop beyond c3 + buffer.",
             "Fills and exits are simulated on H1 bars (same bar stop+target = loss).",
             "`setups` = stories with a qualifying pattern, `filled` = retest happened, `missed` = no retest in time.",
             "`tpN_expR` = average result in R per filled trade (TP1 = next swing / 1.5R min, TP2 = story target).", "",
             f"Settings: `{json.dumps({k: v for k, v in cfg.items() if k != 'story_cfg'})}`", ""]
    if df.empty:
        lines.append("No stories found.")
        open(path, "w").write("\n".join(lines))
        return
    df = df.copy()
    df["year"] = df["tap_time"].str[:4]
    df["tf"] = df.get("tf", pd.Series(index=df.index, dtype=object)).fillna("-")
    lines += ["## Status count", "", df.groupby(["story", "status"]).size().unstack(fill_value=0).to_markdown(), ""]
    sections = [("By story", ["story"]), ("By story and entry TF", ["story", "tf"]),
                ("By story and side", ["story", "side"]), ("By year (D story)", ["year"]),
                ("By pair (D story)", ["pair"]), ("By year (all stories)", ["story", "year"])]
    for title, by in sections:
        d = df[df["story"] == "D"] if "D story" in title else df
        if "entry TF" in title:
            d = d[d["tf"] != "-"]
        if d.empty:
            continue
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
    ap.add_argument("--entry-cfg", default="{}", help="JSON overrides of entry.DEFAULT")
    a = ap.parse_args()
    scfg = {**STORY_DEFAULT, **json.loads(a.cfg)}
    ecfg = {**DEFAULT, "entry_tfs": ENTRY_TFS, **json.loads(a.entry_cfg)}
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for pair in a.pairs.split(","):
        h1 = hourly(pair, a.start, a.end)
        h1 = h1[(h1.index.year >= a.start) & (h1.index.year <= a.end)]
        for st in a.stories.split(","):
            stories = find_stories(pair, h1, st, scfg)
            e = find_entries(pair, h1, stories, ecfg, scfg)
            n = sum(r["status"] == "TRIGGERED" for r in e)
            print(f"{pair} {st}: {len(stories)} stories, {n} entries filled", flush=True)
            rows += e
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(a.out, "entries.csv"), index=False)
    report(df, ecfg, os.path.join(a.out, "ENTRY_REPORT.md"))
    print(open(os.path.join(a.out, "ENTRY_REPORT.md")).read())


if __name__ == "__main__":
    main()
