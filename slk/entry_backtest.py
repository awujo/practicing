"""Backtest the entry model (stage 2) on every confirmed story and write reports/ENTRY_REPORT.md.

python -m slk.entry_backtest --pairs EURUSD,GBPJPY --start 2018 --end 2025 --out reports
"""
import argparse
import json
import os

import pandas as pd

from . import store
from .backtest import PAIRS, run_pairs
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
             "M: W > D) the bot looks for two entry models (column `model`):",
             "- `continuation`: c1-c2 A/V line, c3 wick rejection, breakout on c4 or a later candle (max",
             "  `breakout_max_bars` after c3, no close back through the line first); limit at the line, stop beyond",
             "  the rejection wick + buffer.",
             "- `qmr` (Quasimodo Reversal): shoulder, head beyond it, neck broken by a close; price back in the",
             "  shoulder/neck zone, a trigger-TF (H1 under H4) continuation breakout there, limit at its line; stop",
             "  beyond the head if it fits `max_stop_pips`, else beyond the rejection wick.",
             "A pending QMR is not replaced by a newer continuation level. Stories without a setup show model `-`.",
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
    df["model"] = df.get("model", pd.Series(index=df.index, dtype=object)).fillna("-")
    lines += ["## Status count", "", df.groupby(["story", "status"]).size().unstack(fill_value=0).to_markdown(), ""]
    sections = [("By story", ["story"]), ("By entry model", ["model"]), ("By story and entry model", ["story", "model"]),
                ("By story and entry TF", ["story", "tf"]),
                ("By story and side", ["story", "side"]), ("By year (D story)", ["year"]),
                ("By pair (D story)", ["pair"]), ("By year (all stories)", ["story", "year"])]
    for title, by in sections:
        d = df[df["story"] == "D"] if "D story" in title else df
        if "entry TF" in title:
            d = d[d["tf"] != "-"]
        if "entry model" in title:
            d = d[d["model"] != "-"]
        if d.empty:
            continue
        lines += [f"## {title}", "", summarize(d, by).to_markdown(), ""]
    open(path, "w").write("\n".join(lines))


def pair_entries(pair, start, end, stories, scfg, ecfg):
    h1 = store.hourly(pair, start, end)
    h1 = h1[(h1.index.year >= start) & (h1.index.year <= end)]
    rows = []
    for st in stories:
        found = find_stories(pair, h1, st, scfg)
        e = find_entries(pair, h1, found, ecfg, scfg)
        n = sum(r["status"] == "TRIGGERED" for r in e)
        print(f"{pair} {st}: {len(found)} stories, {n} entries filled", flush=True)
        rows += e
    return rows


def _pair_job(args):
    return pair_entries(*args)


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
    pairs = a.pairs.split(",")
    store.months_all(pairs, a.start, a.end)
    jobs = [(p, a.start, a.end, a.stories.split(","), scfg, ecfg) for p in pairs]
    rows = [r for chunk in run_pairs(_pair_job, jobs) for r in chunk]
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(a.out, "entries.csv"), index=False)
    report(df, ecfg, os.path.join(a.out, "ENTRY_REPORT.md"))
    print(open(os.path.join(a.out, "ENTRY_REPORT.md")).read())


if __name__ == "__main__":
    main()
