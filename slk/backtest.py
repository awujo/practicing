"""Backtest the story-line bias on history and write a report.

python -m slk.backtest --pairs EURUSD,GBPJPY --start 2018 --end 2025 --out reports
python -m slk.backtest ... --variants   # + side-by-side table of the VARIANTS below (REPORT.md "Variants")
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


def _load(pair, start, end):
    try:
        h1 = store.hourly(pair, start, end)
    except RuntimeError as e:  # no candles for this pair (download refused): skip it, keep the other pairs
        print(f"{pair}: skipped ({e})", flush=True)
        return None
    return h1[(h1.index.year >= start) & (h1.index.year <= end)]


def story_rows(pair, h1, stories, cfg, log=True):
    """Story rows of one pair on h1; D stories carry `no_trade` from the M/W filter (M and W are computed for it
    even when not requested, and then dropped)."""
    need = list(stories) + ([s for s in ("W", "M") if s not in stories] if "D" in stories else [])
    found = {st: find_stories(pair, h1, st, cfg) for st in need}
    if "D" in found:
        found["D"] = apply_mw_filter(found["D"], found.get("M", []), found.get("W", []), cfg)
    out = []
    for st in stories:
        if log:
            n_nt = sum(1 for r in found[st] if r.get("no_trade"))
            print(f"{pair} {st}: {len(found[st])} stories" + (f" ({n_nt} NO_TRADE M/W)" if st == "D" else ""),
                  flush=True)
        out += found[st]
    return out


def pair_rows(pair, start, end, stories, cfg):
    """All story rows of one pair (see story_rows)."""
    h1 = _load(pair, start, end)
    return [] if h1 is None else story_rows(pair, h1, stories, cfg)


# ------------------------------------------------------------------ variants (owner picks defaults from data)
# (setting, value, kind, overrides): kind "story" = slk.story cfg (bias trades), "entry" = slk.entry cfg (entry
# trades on the base stories). The first value of each setting is the current default.
VARIANTS = [
    ("next_day_rule", "flag", "story", {"next_day_rule": "flag"}),
    ("next_day_rule", "require", "story", {"next_day_rule": "require"}),
    ("cadjpy_exception", "on", "story", {"cadjpy_exception": True}),
    ("cadjpy_exception", "off", "story", {"cadjpy_exception": False}),
    ("entry_alignment", "d_h4", "entry", {"alignment": "d_h4"}),
    ("entry_alignment", "w_d_h4", "entry", {"alignment": "w_d_h4"}),
    ("entry_alignment", "off", "entry", {"alignment": "off"}),
]


def variant_rows(pair, h1, stories, cfg, ecfg, variants=VARIANTS):
    """(base story rows, variant rows). Each variant row is a story row (kind story) or an entry row (kind entry)
    tagged with `setting`, `value`, `kind`; identical story cfgs are computed once."""
    from .entry import find_entries
    memo = {}

    def run(c):
        k = json.dumps(c, sort_keys=True, default=str)
        if k not in memo:
            memo[k] = story_rows(pair, h1, stories, c, log=False)
        return memo[k]

    base = run(cfg)
    tradable = [r for r in base if not r.get("no_trade")]
    out = []
    for setting, value, kind, ov in variants:
        tag = {"setting": setting, "value": value, "kind": kind}
        if kind == "story":
            out += [{**r, **tag} for r in run({**cfg, **ov})]
        else:
            out += [{**r, **tag} for r in find_entries(pair, h1, tradable, {**ecfg, **ov}, cfg)]
    print(f"{pair}: {len(base)} stories, {len(out)} variant rows", flush=True)
    return base, out


def _variant_job(args):
    pair, start, end, stories, cfg, ecfg = args
    h1 = _load(pair, start, end)
    return ([], []) if h1 is None else variant_rows(pair, h1, stories, cfg, ecfg)


def _score(name, setting, value, R, win):
    n = len(R)
    return {"setting": setting, "variant": name, "value": value, "trades": n,
            "win%": round(float(win.mean()) * 100, 1) if n else None,
            "avg_R": round(float(R.mean()), 3) if n else None, "total_R": round(float(R.sum()), 1) if n else 0.0}


def variants_table(vdf):
    """One line per variant: trades, win rate, average R, total R. Story variants score tradable (not NO_TRADE)
    stories with the trade view (entry at confirmation, stop beyond the tap wick, target); next_day_rule=flag is
    also split into next-day / same-day stories. Entry variants score filled entries (TRIGGERED), TP1 and TP2."""
    rows = []
    if vdf is None or vdf.empty:
        return pd.DataFrame(rows)
    for (setting, value, kind), d in vdf.groupby(["setting", "value", "kind"], sort=False):
        if kind == "story":
            d = d[~d.get("no_trade", pd.Series(False, index=d.index)).fillna(False).astype(bool)]
            rows.append(_score(f"{setting}={value}", setting, value, d["result_R"], d["outcome"] == "win"))
            if setting == "next_day_rule" and value == "flag" and "next_day" in d:
                for lab, m in (("next-day breakouts only", d["next_day"] == True),  # noqa: E712
                               ("same-day breakouts only", d["next_day"] == False),  # noqa: E712
                               ("no breakout (cadjpy, n/a)", d["next_day"].isna())):
                    x = d[m]
                    rows.append(_score(f"  flag: {lab}", setting, value, x["result_R"], x["outcome"] == "win"))
        else:
            t = d[d["status"] == "TRIGGERED"] if "status" in d else d.iloc[0:0]
            for tp in ("tp1", "tp2"):
                if f"{tp}_R" not in t:
                    rows.append(_score(f"{setting}={value} ({tp.upper()})", setting, value, pd.Series(dtype=float),
                                       pd.Series(dtype=bool)))
                    continue
                rows.append(_score(f"{setting}={value} ({tp.upper()})", setting, value, t[f"{tp}_R"],
                                   t[f"{tp}_outcome"] == "win"))
    return pd.DataFrame(rows)


def variants_section(vdf):
    tab = variants_table(vdf)
    lines = ["## Variants (side by side, to choose defaults)", "",
             "Same pairs and years for every line. Bias variants: tradable stories, trade view (entry at the",
             "confirmation close, stop beyond the tap wick + buffer, target), `win%` = target before stop, `avg_R` /",
             "`total_R` = result in R. Entry variants: filled entries on the default-rule stories, TP1 and TP2.",
             "First value of each setting = current default.", ""]
    if tab.empty:
        return lines + ["No variant rows.", ""]
    return lines + [tab.drop(columns=["setting", "value"]).set_index("variant").to_markdown(), ""]


def _pair_job(args):
    return pair_rows(*args)


def run_pairs(fn, jobs, workers=None):
    """fn(job) for every job in a process pool (CPU-bound engine), results in job order."""
    workers = workers or int(os.environ.get("SLK_WORKERS", "0") or 0) or (os.cpu_count() or 1)
    if workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(min(workers, len(jobs))) as ex:
            return list(ex.map(fn, jobs))
    return [fn(j) for j in jobs]


def report(df, cfg, path, variants=None):
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
        if "next_day" in df:
            nd = df[df["next_day"].notna()].assign(next_day=lambda x: x["next_day"].map(
                {True: "next day", False: "same day"}))
            if not nd.empty:
                lines += ["## By story and Next Day Rule (label)", "", summarize(nd, ["story", "next_day"]).to_markdown(), ""]
    if variants is not None:
        lines += variants_section(variants)
    open(path, "w").write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=",".join(PAIRS))
    ap.add_argument("--start", type=int, default=2018)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--stories", default="D,W,M")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--cfg", default="{}", help="JSON overrides of story.DEFAULT")
    ap.add_argument("--entry-cfg", default="{}", help="JSON overrides of entry.DEFAULT (entry variants)")
    ap.add_argument("--variants", action="store_true", help="also compare VARIANTS side by side")
    a = ap.parse_args()
    cfg = {**DEFAULT, **json.loads(a.cfg)}
    os.makedirs(a.out, exist_ok=True)
    pairs, stories = a.pairs.split(","), a.stories.split(",")
    store.months_all(pairs, a.start, a.end)  # candle store: only missing months are downloaded (cTrader first)
    store.close_feed()  # before the process pool forks
    vdf = None
    if a.variants:
        from .entry import DEFAULT as EDEF, ENTRY_TFS
        ecfg = {**EDEF, "entry_tfs": ENTRY_TFS, **json.loads(a.entry_cfg)}
        res = run_pairs(_variant_job, [(p, a.start, a.end, stories, cfg, ecfg) for p in pairs])
        rows = [r for base, _ in res for r in base]
        vdf = pd.DataFrame([r for _, v in res for r in v])
        vdf.to_csv(os.path.join(a.out, "variants.csv"), index=False)
    else:
        rows = [r for chunk in run_pairs(_pair_job, [(p, a.start, a.end, stories, cfg) for p in pairs]) for r in chunk]
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(a.out, "stories.csv"), index=False)
    report(df, cfg, os.path.join(a.out, "REPORT.md"), vdf)
    print(open(os.path.join(a.out, "REPORT.md")).read())


if __name__ == "__main__":
    main()
