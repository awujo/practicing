"""Replay checks: Kevin King's own worked bias examples run through the live bias engine (slk.live.pair_state, the
same code the hourly runner uses) on real Dukascopy candles from the candle store. Writes reports/EXAMPLES.md.

    python -m slk.verify_examples [--out reports] [--only CADJPY]

Each example is a story Kevin drew in class, with the date/price read from the transcript and the frames
(knowledge-base/study/notes_storyline.md §3, frames_D/A2/H). Kinds:
  BIAS      a confirmed story (CONFIRMED / TARGET_HIT / INVALIDATED / ENDED_FLIP / CANCELLED) with its tap in the
            window, on the expected side, origin level within the tolerance, and (if given) built by `rule` (target
            is shown, not judged);
  NO_TRADE  at `now` (the class time) no tradable confirmed story with a tap in the window ("no H4 breakout ->
            no trade"); a TAPPED row is fine and is shown;
  SIDE      every tradable confirmed story of `stories` confirmed in the window is on the expected side (>= 1).
Always exits 0 (examples that fail are marked FAIL in the report); a crash of one example is marked ERROR.
Dukascopy is blocked in Claude's sandbox, so this runs on GitHub Actions (.github/workflows/verify-examples.yml).
"""
import argparse
import os
import traceback
from datetime import datetime, timezone

import pandas as pd

from .candles import _key
from .story import STORIES

CONFIRMED = ("CONFIRMED", "TARGET_HIT", "INVALIDATED", "ENDED_FLIP", "CANCELLED")

# day windows are trading days (17:00 New York close); `now` is UTC
EXAMPLES = [
    {"id": "cadjpy-d-buy", "pair": "CADJPY", "kind": "BIAS", "story": "D", "side": "BUY",
     "tap": ("2026-01-06", "2026-01-09"), "origin": 112.903, "tol": 0.15, "target": 114.65,
     "now": "2026-02-07 00:00",
     "evidence": "story-line-pt2@686-1980; F story-line-pt2/sheet_013-016 (OC level 112.903, daily wick tap Jan 8 "
                 "2026), sheet_015-021 (4H replay, last small close peak ~113.2 = B, 'bms'), sheet_025-028 "
                 "(target 114.65 hit)"},
    {"id": "cadjpy-d-buy-no-h4-exception", "pair": "CADJPY", "kind": "BIAS", "story": "D", "side": "BUY",
     "tap": ("2026-01-28", "2026-02-02"), "origin": 113.2, "tol": 0.30, "target": 114.466, "rule": "cadjpy",
     "now": "2026-02-03 00:00",
     "evidence": "REVIEW #31c. cadjpy-bd@400-995 ('price did a sweep of previous day low into the daily open close "
                 "level, when we are already bullish on the weekly ... direction is confirmed ... you really do not "
                 "need to be waiting for this breakout'); F cadjpy-bd/sheet_008-009 (line ~113.2, sweep candle closes "
                 "above, 'target' 114.466 drawn at once, replay to Mon Feb 2 2026)"},
    {"id": "eurgbp-d-buy-overlap", "pair": "EURGBP", "kind": "BIAS", "story": "D", "side": "BUY",
     "tap": ("2026-01-09", "2026-01-16"), "origin": 0.8657, "tol": 0.0012, "target": 0.8722,
     "now": "2026-01-24 00:00",
     "evidence": "REVIEW #31a/#30. all-in-1@1424-1620 ('weekly and daily are using exactly this key level ... it "
                 "becomes daily reject daily ... we take our profit at this key level'); F all-in-1/sheet_020-027 "
                 "(EURGBP W=D V ~0.8657, 4H EXB, TP at the next KL 0.8722, hit). Target shown, not judged"},
    {"id": "gbpjpy-d-no-h4-breakout", "pair": "GBPJPY", "kind": "NO_TRADE", "story": "D", "side": "BUY",
     "tap": ("2026-01-19", "2026-01-20"), "origin": 210.809, "tol": 0.20, "now": "2026-01-20 04:00",
     "evidence": "story-line-pt4@204-830 ('can we say the daily is bullish? No... breakout has not been "
                 "confirmed', 'no storyline, no trade'); F story-line-pt4/sheet_009 (D level 210.809, Mon Jan 19 "
                 "2026, class Tue Jan 20 ~04:20 UTC)"},
    {"id": "usdjpy-d-no-h4-breakout", "pair": "USDJPY", "kind": "NO_TRADE", "story": "D", "side": None,
     "tap": ("2026-01-19", "2026-01-20"), "origin": None, "tol": None, "now": "2026-01-20 04:30",
     "evidence": "story-line-pt4@840-1210 (USDJPY same as GBPJPY: no H4 breakout, no trade); F story-line-pt4/"
                 "sheet_015 (H4 levels 158.141 / 157.477)"},
    {"id": "usdcad-d-sell-friday-sweep", "pair": "USDCAD", "kind": "BIAS", "story": "D", "side": "SELL",
     "tap": ("2026-01-15", "2026-01-19"), "origin": 1.39201, "tol": 0.0020, "target": None,
     "now": "2026-01-24 00:00",
     "evidence": "story-line-pt4@1229-1520 (sweep of previous day/week high into a fresh daily open-close KL, "
                 "'daily reject daily', close below the last V before the tap = bearish, TP1/TP2 hit); "
                 "F story-line-pt4/sheet_018-019 (KL 1.39201, V ~1.3890, 4H break Mon Jan 19 2026)"},
    {"id": "euraud-sells", "pair": "EURAUD", "kind": "SIDE", "stories": ["W", "D"], "side": "SELL",
     "window": ("2026-01-15", "2026-02-21"), "now": "2026-02-21 00:00",
     "evidence": "weekly-recap@151-1000 ('weekly BOS down plus daily BOS down means only sells'); F weekly-recap/"
                 "sheet_005-017 (weekly close below 1.7172, daily swing-low ladder, H4 sell 1.6800 -> B 1.6620, "
                 "chart up to Fri Feb 20 2026)"},
    {"id": "gbpaud-sells", "pair": "GBPAUD", "kind": "SIDE", "stories": ["W", "D"], "side": "SELL",
     "window": ("2026-01-15", "2026-02-21"), "now": "2026-02-21 00:00",
     "evidence": "weekly-recap@440-1000; F weekly-recap/sheet_006-019 (daily ladder 1.9750/1.9590/1.9500/1.9110, "
                 "H4 A-level 1.9143, sell to 1.9029)"},
    {"id": "usdchf-d-reject-no-h4", "pair": "USDCHF", "kind": "NO_TRADE", "story": "D", "side": "BUY",
     "tap": ("2026-01-20", "2026-01-20"), "origin": 0.7890, "tol": 0.0015, "now": "2026-01-21 00:00",
     "evidence": "class-wrok@77-640 (daily sweep + daily reject at the range-low KL 0.7890, no H4 breakout -> "
                 "'we have to wait for the day to close', no daily-story trade; the trade came next day from an "
                 "H4 level + 1H breakout); F class-wrok/sheet_003-006 (Jan 20 2026)"},
]


def _day(t, tf):
    """Trading-day label (17:00 New York close) of an origin bar start, as YYYY-MM-DD."""
    return str(_key(pd.DatetimeIndex([pd.Timestamp(t).tz_localize("UTC") if pd.Timestamp(t).tzinfo is None
                                      else pd.Timestamp(t)]), "D")[0].date())


def _in(day, win):
    return win[0] <= day <= win[1]


def _fmt(pair, x):
    if x is None:
        return "-"
    return f"{x:.3f}" if pair.endswith("JPY") else f"{x:.5f}"


def _desc(pair, r):
    return (f"{r['story']} {r['side']} {r['status']} [{r.get('rule') or 'standard'}]{' NO_TRADE(' + r.get('no_trade_reason', '') + ')' if r.get('no_trade') else ''}"
            f" level {_fmt(pair, r['level'])} ({r.get('level_kind')}) B {_fmt(pair, r['point_b'])}"
            f" target {_fmt(pair, r['target'])} tap {_day(r['tap_time'], 'D')}"
            + (f" confirmed {str(r['confirm_time'])[:16]}" if r.get("confirm_time") else "")
            + (f" ended: {r['end_reason']}" if r.get("end_reason") else ""))


def load(pair, now):
    from . import store
    end = pd.Timestamp(now)
    h1 = store.hourly(pair, end.year - 4, end.year, now=datetime.now(timezone.utc))
    return h1


def check(ex, h1, cfg=None):
    """(result 'PASS'/'FAIL', found text) for one example on H1 candles `h1` (UTC index)."""
    from .live import build_cfg, pair_state
    cfg = cfg or build_cfg()[0]
    now = pd.Timestamp(ex["now"], tz="UTC")
    stories = ["D", "W", "M"]  # all three: the M/W conflict check for D needs them (as in the live runner)
    rows = pair_state(ex["pair"], h1[h1.index < now], now, stories, cfg)
    p = ex["pair"]
    if ex["kind"] == "SIDE":
        got = [r for r in rows if r["story"] in ex["stories"] and r["status"] in CONFIRMED and r.get("confirm_time")
               and _in(str(pd.Timestamp(r["confirm_time"]).date()), ex["window"])]
        trad = [r for r in got if not r.get("no_trade")]
        ok = bool(trad) and all(r["side"] == ex["side"] for r in trad)
        return ("PASS" if ok else "FAIL"), ("; ".join(_desc(p, r) for r in got) or "no confirmed W/D story in window")
    win = [r for r in rows if r["story"] == ex["story"] and _in(_day(r["tap_time"], STORIES[ex["story"]][0]), ex["tap"])]
    conf = [r for r in win if r["status"] in CONFIRMED and not r.get("no_trade")]
    text = "; ".join(_desc(p, r) for r in win) or "no tap of a fresh trend level in the window"
    if ex["kind"] == "NO_TRADE":
        return ("PASS" if not conf else "FAIL"), text
    good = [r for r in conf if r["side"] == ex["side"]
            and (ex.get("origin") is None or abs(r["level"] - ex["origin"]) <= ex["tol"])
            and (not ex.get("rule") or str(r.get("rule") or "").startswith(ex["rule"]))]
    return ("PASS" if good else "FAIL"), text


def expected(ex):
    p = ex["pair"]
    if ex["kind"] == "SIDE":
        return f"{'/'.join(ex['stories'])} stories confirmed {ex['window'][0]}..{ex['window'][1]}: only {ex['side']}"
    if ex["kind"] == "NO_TRADE":
        s = f"{ex['story']} NO_TRADE at {ex['now']} UTC (tap {ex['tap'][0]}..{ex['tap'][1]})"
        return s + (f", level ~{_fmt(p, ex['origin'])}" if ex.get("origin") else "")
    s = f"{ex['story']} {ex['side']}, tap {ex['tap'][0]}..{ex['tap'][1]}, origin {_fmt(p, ex['origin'])} ± {ex['tol']}"
    if ex.get("rule"):
        s += f", rule {ex['rule']}"
    return s + (f", target ~{_fmt(p, ex['target'])}" if ex.get("target") else "")


def report(results):
    n = sum(1 for r in results if r["result"] == "PASS")
    lines = ["# Kevin's worked examples: replay check", "",
             f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m slk.verify_examples` "
             "(live bias engine `slk.live.pair_state`, code defaults, Dukascopy H1 from the candle store).", "",
             f"**{n}/{len(results)} PASS.** A FAIL is a story the bot reads differently from Kevin; it does not stop "
             "the workflow. Evidence = transcript [video@sec] and frame sheets (knowledge-base/frames).", "",
             "| Result | Example | Expected (Kevin) | Bot found | Evidence |", "|---|---|---|---|---|"]
    esc = lambda s: str(s).replace("|", "/").replace("\n", " ")  # noqa: E731
    for r in results:
        lines.append(f"| **{r['result']}** | {r['id']} ({r['pair']}) | {esc(r['expected'])} | {esc(r['found'])} | "
                     f"{esc(r['evidence'])} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports")
    ap.add_argument("--only", default="", help="comma list of pairs or example ids")
    a = ap.parse_args(argv)
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    results = []
    for ex in EXAMPLES:
        if only and ex["pair"] not in only and ex["id"] not in only:
            continue
        row = {"id": ex["id"], "pair": ex["pair"], "expected": expected(ex), "evidence": ex["evidence"]}
        try:
            row["result"], row["found"] = check(ex, load(ex["pair"], ex["now"]))
        except Exception as e:  # one broken example must not hide the others
            row["result"], row["found"] = "ERROR", f"{type(e).__name__}: {e}"
            traceback.print_exc()
        print(f"{row['result']:5} {ex['id']}: {row['found']}", flush=True)
        results.append(row)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "EXAMPLES.md"), "w") as f:
        f.write(report(results))
    print(f"{sum(r['result'] == 'PASS' for r in results)}/{len(results)} PASS -> {a.out}/EXAMPLES.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
