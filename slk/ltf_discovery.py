"""Study 3 (research/TREND_LTF_PLAN.md): which lower-TF condition at the entry makes a trade more likely to work?

Input: pattern_trades.csv.gz of slk.trend_study (one row per Kevin continuation level and entry kind, with the
slk.ltf_features columns, all measured from candles closed at the entry). Method, fixed BEFORE looking at results:
  1. Split by year: TRAIN = years < split, TEST = years >= split. Everything is chosen on TRAIN only.
  2. Every feature is cut into buckets: booleans / categories as they are, numbers into 3 equal-count buckets
     (tertile cut points from TRAIN).
  3. A bucket is a CANDIDATE when on TRAIN it has >= MIN_N trades and its avg R beats the TRAIN baseline of the
     same entry TF / entry kind by >= MIN_LIFT R, for the outcome column (default R_3R: fixed 3R target).
  4. Candidates are then shown on TEST once. A rule "holds" when TEST n >= MIN_N_TEST, TEST avg R beats the TEST
     baseline by >= MIN_LIFT and TEST avg R > 0 after costs.
  5. Pairs of two candidates (AND) are tried the same way (train-chosen, test-checked).
  6. Chance level: the same screen on the same trades with the outcome shuffled within tf / entry / train-test
     (CHANCE_SEEDS runs). Real "holds" well above that mean are worth a look; at or below it they are luck.
Caveats (verifier agent 2026-10-20): rows overlap (one row per level and TF; ~half are within 24 h of another
same-pair same-side row), so n overstates the independent sample; the flat cost (1.2 pips / stop) makes wide-stop
buckets look better by construction; hours 20-23 UTC (rollover) have bid spikes the flat cost does not cover.
Many buckets are tested, so some TRAIN winners are luck: only TEST decides, and even a TEST pass on 8 pairs is a
lead for the full 28-pair run, not a rule. No ANN. Nothing here changes the live bot.

    python -m slk.ltf_discovery --trades reports/pattern_trades.csv.gz --split 2023 --out reports
"""
import argparse
import itertools
import os

import numpy as np
import pandas as pd

MIN_N = 100
MIN_N_TEST = 50
MIN_LIFT = 0.10
CHANCE_SEEDS = 10
BOOL = ("fvg", "sweep", "h1_trend_agrees", "d_trend_agrees", "w_trend_agrees", "h4_break_agrees",
        "d_break_agrees", "w_break_agrees")
CAT = ("session", "daily", "h4_story", "side", "stop_at", "dow")
NUM = ("stop_pips", "stop_atr", "atr_pips", "break_body_atr", "break_close_pos", "run_R", "hours_tap_to_entry",
       "prev_day_pos", "bo_body_x_avg", "bo_candle", "hours_to_fill", "fvg_pips")


def buckets(train, col):
    """{label: mask function} for one feature, cut points from TRAIN."""
    if col in BOOL:
        return {f"{col}=yes": lambda d, c=col: d[c] == True,  # noqa: E712 (column may hold None)
                f"{col}=no": lambda d, c=col: d[c] == False}  # noqa: E712
    if col in CAT:
        return {f"{col}={v}": (lambda d, c=col, v=v: d[c] == v) for v in sorted(train[col].dropna().unique(), key=str)}
    x = pd.to_numeric(train[col], errors="coerce").dropna()
    if x.nunique() < 3:
        return {}
    q1, q2 = np.quantile(x, [1 / 3, 2 / 3])
    if q1 == q2:
        return {f"{col}<={q1:g}": lambda d, c=col, a=q1: pd.to_numeric(d[c], errors="coerce") <= a,
                f"{col}>{q1:g}": lambda d, c=col, a=q1: pd.to_numeric(d[c], errors="coerce") > a}
    return {f"{col}<={q1:g}": lambda d, c=col, a=q1: pd.to_numeric(d[c], errors="coerce") <= a,
            f"{q1:g}<{col}<={q2:g}": lambda d, c=col, a=q1, b=q2: pd.to_numeric(d[c], errors="coerce").between(a, b, inclusive="right"),
            f"{col}>{q2:g}": lambda d, c=col, b=q2: pd.to_numeric(d[c], errors="coerce") > b}


def screen(df, split, out_col="R_3R"):
    rows, picks = [], []
    for (tf, kind), g in df.groupby(["tf", "entry"]):
        tr, te = g[g["year"] < split], g[g["year"] >= split]
        if len(tr) < MIN_N or not len(te):
            continue
        b_tr, b_te = tr[out_col].mean(), te[out_col].mean()
        cands = []
        for col in BOOL + CAT + NUM:
            if col not in g:
                continue
            for lab, m in buckets(tr, col).items():
                a, b = tr[m(tr).fillna(False).astype(bool)], te[m(te).fillna(False).astype(bool)]
                r = {"tf": tf, "entry": kind, "rule": lab, "train n": len(a),
                     "train avg R": round(a[out_col].mean(), 3) if len(a) else np.nan,
                     "train base": round(b_tr, 3), "test n": len(b),
                     "test avg R": round(b[out_col].mean(), 3) if len(b) else np.nan, "test base": round(b_te, 3)}
                r["candidate"] = len(a) >= MIN_N and r["train avg R"] - b_tr >= MIN_LIFT
                r["holds"] = bool(r["candidate"] and len(b) >= MIN_N_TEST and r["test avg R"] - b_te >= MIN_LIFT
                                  and r["test avg R"] > 0)
                rows.append(r)
                if r["candidate"]:
                    cands.append((lab, m))
        for (l1, m1), (l2, m2) in itertools.combinations(cands, 2):
            if l1.split("=")[0].split("<")[0] == l2.split("=")[0].split("<")[0]:
                continue
            mt = m1(tr).fillna(False).astype(bool) & m2(tr).fillna(False).astype(bool)
            me = m1(te).fillna(False).astype(bool) & m2(te).fillna(False).astype(bool)
            a, b = tr[mt], te[me]
            if len(a) < MIN_N:
                continue
            r = {"tf": tf, "entry": kind, "rule": f"{l1} AND {l2}", "train n": len(a),
                 "train avg R": round(a[out_col].mean(), 3), "train base": round(b_tr, 3), "test n": len(b),
                 "test avg R": round(b[out_col].mean(), 3) if len(b) else np.nan, "test base": round(b_te, 3)}
            r["candidate"] = r["train avg R"] - b_tr >= MIN_LIFT
            r["holds"] = bool(r["candidate"] and len(b) >= MIN_N_TEST and r["test avg R"] - b_te >= MIN_LIFT
                              and r["test avg R"] > 0)
            picks.append(r)
    return pd.DataFrame(rows), pd.DataFrame(picks)


def best_target(df, split):
    """Which fixed target (1R .. 5R) is best per TF / entry, train vs test (the 'higher fixed reward' question)."""
    rows = []
    for (tf, kind), g in df.groupby(["tf", "entry"]):
        for part, d in (("train", g[g["year"] < split]), ("test", g[g["year"] >= split])):
            r = {"tf": tf, "entry": kind, "part": part, "n": len(d)}
            for c in ("R_1R", "R_2R", "R_3R", "R_5R"):
                r[c] = round(d[c].mean(), 3) if len(d) else np.nan
            rows.append(r)
    return pd.DataFrame(rows)


def chance(df, split, out_col, seeds=CHANCE_SEEDS):
    """Mean / max number of single and pair 'holds' with the outcome shuffled within tf / entry / train-test."""
    part = (df["year"] >= split).astype(int)
    res = []
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        sh = df.copy()
        sh[out_col] = sh.groupby([sh["tf"], sh["entry"], part])[out_col].transform(lambda x: rng.permutation(x.to_numpy()))
        s, p = screen(sh, split, out_col)
        res.append((int(s["holds"].sum()) if len(s) else 0, int(p["holds"].sum()) if len(p) else 0))
    a = np.array(res)
    return a.mean(0).round(1), a.max(0)


def report(df, split, out_col, seeds=CHANCE_SEEDS):
    single, pairs = screen(df, split, out_col)
    if seeds:
        mean, mx = chance(df, split, out_col, seeds)
        luck = (f"\n\nChance level ({seeds} shuffles of {out_col}): single holds mean {mean[0]} (max {mx[0]}), "
                f"two-condition holds mean {mean[1]} (max {mx[1]}). Real: single "
                f"{int(single['holds'].sum()) if len(single) else 0}, two-condition "
                f"{int(pairs['holds'].sum()) if len(pairs) else 0}.")
    else:
        luck = ""
    txt = ("# Lower-TF discovery\n\n" + (__doc__ or "") +
           f"\n\nTrades: {len(df)}, {df['pair'].nunique()} pairs, years {df['year'].min()}-{df['year'].max()}; "
           f"train < {split} <= test. Outcome: {out_col} (cost included)." + luck + "\n\n## Best fixed target\n\n" +
           best_target(df, split).to_markdown(index=False) + "\n")
    for name, t in (("Single conditions", single), ("Two conditions (AND)", pairs)):
        if t.empty:
            txt += f"\n## {name}\n\nnone\n"
            continue
        held = t[t["holds"]]
        cand = t[t["candidate"]].sort_values("train avg R", ascending=False)
        txt += (f"\n## {name}: held on TEST ({len(held)} of {len(cand)} train candidates, {len(t)} tested)\n\n" +
                (held.drop(columns=["candidate", "holds"]).to_markdown(index=False) if len(held) else "none") +
                f"\n\n## {name}: all TRAIN candidates (top 40 by train avg R)\n\n" +
                (cand.head(40).drop(columns=["candidate"]).to_markdown(index=False) if len(cand) else "none") + "\n")
    return txt, single, pairs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", required=True)
    ap.add_argument("--split", type=int, default=2023)
    ap.add_argument("--outcome", default="R_3R")
    ap.add_argument("--seeds", type=int, default=CHANCE_SEEDS, help="chance-level shuffles (0 = off)")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    df = pd.read_csv(a.trades)
    txt, single, pairs = report(df, a.split, a.outcome, a.seeds)
    print(txt)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        open(os.path.join(a.out, "LTF_DISCOVERY.md"), "w").write(txt)
        single.to_csv(os.path.join(a.out, "ltf_single.csv"), index=False)
        pairs.to_csv(os.path.join(a.out, "ltf_pairs.csv"), index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
