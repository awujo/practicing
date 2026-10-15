"""Replay Kevin's own trades (tests/kevin_trades.json: pair, side, entry TF, time, entry, stop, TP) through the bias
engine + entry model and write reports/KEVIN_TRADES.md.

A trade PASSES when the bot has a filled entry on the same pair and side whose fill is within 3 days of Kevin's
time, with its entry and stop each within 5 pips of his. Data: the H1 CSVs of the examples (data/examples) or the
candle store.

python -m slk.verify_trades --data data/examples [--entry-cfg '{"qmr_entry": "neck"}']
"""
import argparse
import json
import os

import pandas as pd

from .entry import DEFAULT as ENTRY_DEFAULT, ENTRY_TFS, find_entries
from .instruments import pip
from .story import DEFAULT as STORY_DEFAULT, find_stories
from .verify_examples import load_csv

TRADES = os.path.join(os.path.dirname(__file__), "..", "tests", "kevin_trades.json")


def load_trades(path=TRADES):
    with open(path) as f:
        return json.load(f)


def bot_entries(pair, h1, scfg, ecfg, stories=("D", "W", "M")):
    rows = []
    for st in stories:
        rows += find_entries(pair, h1, find_stories(pair, h1, st, scfg), ecfg, scfg)
    return rows


def check(tr, rows, days=3.0, pips=5.0):
    """('PASS' | 'FAIL', best matching bot entry or None, note)."""
    P = pip(tr["pair"])
    t = pd.Timestamp(tr["time"])
    best, score = None, None
    for r in rows:
        if r.get("side") != tr["side"] or r.get("status") not in ("TRIGGERED", "MISSED", "PENDING"):
            continue
        rt = pd.Timestamp(r.get("fill_time") or r.get("created_time"))
        dd = abs((rt - t).total_seconds()) / 86400
        de, ds = abs(r["entry"] - tr["entry"]) / P, abs(r["stop"] - tr["stop"]) / P
        sc = dd + (de + ds) / 10
        if score is None or sc < score:
            best, score = {**r, "_days": dd, "_de": de, "_ds": ds}, sc
    if best is None:
        return "FAIL", None, "no bot entry on this side"
    ok = best["status"] == "TRIGGERED" and best["_days"] <= days and best["_de"] <= pips and best["_ds"] <= pips
    note = (f"{best['status']} {best.get('model')} {best.get('tf')}: entry off {best['_de']:.1f} pips, stop off "
            f"{best['_ds']:.1f} pips, {best['_days']:.1f} days from Kevin's time")
    return ("PASS" if ok else "FAIL"), best, note


def run(data, scfg, ecfg, days=3.0, pips=5.0):
    out, cache = [], {}
    for tr in load_trades():
        if tr["pair"] not in cache:
            try:
                h1 = load_csv(tr["pair"], data) if data else None
            except FileNotFoundError:
                h1 = None
            cache[tr["pair"]] = bot_entries(tr["pair"], h1, scfg, ecfg) if h1 is not None else None
        rows = cache[tr["pair"]]
        if rows is None:
            out.append((tr, "NO DATA", None, f"no H1 data for {tr['pair']}"))
            continue
        out.append((tr, *check(tr, rows, days, pips)))
    return out


def report(res, ecfg, path):
    n = sum(r[1] == "PASS" for r in res)
    lines = ["# Kevin's trades: replay check", "",
             f"**{n}/{len(res)} PASS** (same pair and side, filled within 3 days of his time, entry and stop each",
             "within 5 pips). Source of each trade: tests/kevin_trades.json (transcript + frames).", "",
             f"Entry settings: `qmr_entry` = {ecfg.get('qmr_entry')}, `qmr_stop_pips` = {ecfg.get('qmr_stop_pips')}, "
             f"`entry_tfs` = {json.dumps({k: list(v) for k, v in ecfg['entry_tfs'].items()})}", "",
             "| Result | Trade | Kevin (entry / stop / TP) | Bot | Bot result |", "|---|---|---|---|---|"]
    for tr, res_, b, note in res:
        kev = f"{tr['tf']} {tr['side']} {tr['time']}: {tr['entry']} / {tr['stop']} / {tr['tp']}"
        if b is None:
            bot, outc = note, "-"
        else:
            bot = (f"{b.get('tf')} {b.get('model')} {b['side']} fill {b.get('fill_time') or '-'}: {b['entry']:.5g} / "
                   f"{b['stop']:.5g} / TP1 {b['tp1']:.5g} TP2 {b['tp2']:.5g} ({note})")
            outc = f"TP1 {b.get('tp1_outcome') or '-'}, TP2 {b.get('tp2_outcome') or '-'}"
        lines.append(f"| **{res_}** | {tr['id']} | {kev} | {bot} | {outc} |")
    open(path, "w").write("\n".join(lines) + "\n")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/examples")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--cfg", default="{}", help="JSON overrides of story.DEFAULT")
    ap.add_argument("--entry-cfg", default="{}", help="JSON overrides of entry.DEFAULT")
    a = ap.parse_args()
    scfg = {**STORY_DEFAULT, **json.loads(a.cfg)}
    ecfg = {**ENTRY_DEFAULT, "entry_tfs": ENTRY_TFS, **json.loads(a.entry_cfg)}
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "KEVIN_TRADES.md")
    res = run(a.data, scfg, ecfg)
    report(res, ecfg, path)
    print(open(path).read())


if __name__ == "__main__":
    main()
