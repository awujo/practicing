"""Live bias runner (GitHub Actions, hourly). STRATEGY §2, CONTRACT.md.

For every pair: download recent H1 candles, drop still-forming bars, run the story line for D/W/M,
add the current TAPPED (not yet confirmed) story, sync table `bias`, and send Telegram alerts when a story is
newly TAPPED / CONFIRMED or ends (TARGET_HIT / INVALIDATED). Once a day (first run after 17:05 New York) a
summary with one line per pair.

python -m slk.live              # needs DATABASE_URL (+ TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
python -m slk.live --dry-run --pairs EURUSD   # no DB, no Telegram: print what it would store/send
"""
import argparse
import copy
import hashlib
import json
import os
import pickle
import sys
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import settings as S
from . import store as candles_store
from .backtest import PAIRS
from .candles import _key, resample
from .entry import DEFAULT as ENTRY_DEFAULT
from .story import DEFAULT, STORIES, current_tap, find_stories, mw_conflict, pip

JOB = "live"
HISTORY_DAYS = 3 * 365 + 30       # enough months for M/W stories
ALERT_WINDOW = timedelta(hours=36)  # a story first seen by the bot is announced only if this fresh
ACTIVE = ("TAPPED", "CONFIRMED")
ALERT_ON = ("TAPPED", "CONFIRMED", "TARGET_HIT", "INVALIDATED")
BAR_LEN = {"H1": pd.Timedelta(hours=1), "H4": pd.Timedelta(hours=4), "D": pd.Timedelta(days=1),
           "W": pd.Timedelta(days=5)}  # a week closes Friday 17:00 New York (shifted Saturday 00:00)


# ------------------------------------------------------------------ candles
def recent(pair, days):
    """Engine candles of one pair from the candle store (slk/store.py); tests replace this."""
    return candles_store.recent(pair, days)


def prepare_candles(pairs, now):
    """Download only the new bars of every pair into the store (threads). Returns {pair: error}."""
    return candles_store.update_all(pairs, now, days=HISTORY_DAYS)


def _ts(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def drop_forming(h1, tf, now):
    """H1 data cut so that the last bar of `tf` is closed at `now` (UTC): the still-forming H1 hour and the
    hours of a still-forming tf bar are removed."""
    now = _ts(now)
    h1 = h1[h1.index + pd.Timedelta(hours=1) <= now]
    if tf == "H1" or h1.empty:
        return h1
    keys = _key(h1.index, tf)
    last = keys[-1]
    now_shift = _key(pd.DatetimeIndex([now]), "H4")[0] + (now - now.floor("4h"))  # NY-17:00-shifted clock
    if tf == "M":
        end = last + pd.offsets.MonthBegin(1)
    else:
        end = last + BAR_LEN[tf]
    if now_shift >= end:
        return h1
    return h1[keys != last]


# ------------------------------------------------------------------ stories -> bias rows
def _dt(s):
    return None if s is None or (isinstance(s, float) and pd.isna(s)) else pd.Timestamp(s).to_pydatetime().replace(tzinfo=None)


def to_row(s, status):
    return {"pair": s["pair"], "story": s["story"], "side": s["side"], "status": status,
            "level_kind": s.get("level_kind"), "level": float(s["level"]), "point_b": float(s["B"]),
            "target": None if s.get("target") is None else float(s["target"]),
            "invalidation": float(s["level"]), "tap_time": _dt(s["tap_time"]),
            "confirm_time": _dt(s.get("confirm_time"))}


def _beyond_target(row, bars):
    if row["target"] is None or bars.empty:
        return False
    return bool((bars["low"] <= row["target"]).any() if row["side"] == "SELL" else (bars["high"] >= row["target"]).any())


def _closed_through(row, ob):
    """Origin-TF body close back through the level after the tap bar = invalidated."""
    after = ob[pd.to_datetime(ob["start"]) > _ts(row["tap_time"])]
    if after.empty:
        return False
    return bool((after["close"] > row["level"]).any() if row["side"] == "SELL" else (after["close"] < row["level"]).any())


def resolve(row, h1, now, cfg):
    """Status of a stored story that the engine no longer reports (e.g. a TAPPED that went nowhere)."""
    otf = STORIES[row["story"]][0]
    ob = resample(drop_forming(h1, otf, now), otf)
    if row["status"] == "CONFIRMED" and row.get("confirm_time"):
        if _beyond_target(row, h1[h1.index >= _ts(row["confirm_time"])]):
            return "TARGET_HIT"
    if _closed_through(row, ob):
        return "INVALIDATED"
    since = int((pd.to_datetime(ob["start"]) > _ts(row.get("confirm_time") or row["tap_time"])).sum())
    limit = cfg["max_hold"] if row["status"] == "CONFIRMED" else cfg["max_wait"]
    return "CANCELLED" if since > limit else row["status"]


_SRC = os.path.dirname(os.path.abspath(__file__))
ENGINE_VERSION = hashlib.sha1(b"".join(open(os.path.join(_SRC, f), "rb").read() for f in
                                       ("story.py", "levels.py", "structure.py", "candles.py"))).hexdigest()


def _digest(h, story, cfg):
    """Fingerprint of everything find_stories/current_tap see: engine code, story, cfg and the closed bars."""
    m = hashlib.sha1(f"{ENGINE_VERSION}|{story}|{json.dumps(cfg, sort_keys=True, default=str)}".encode())
    m.update(h.index.asi8.tobytes())
    m.update(str(h.index.dtype).encode())
    m.update(np.ascontiguousarray(h[["open", "high", "low", "close"]].to_numpy(float)).tobytes())
    return m.hexdigest()


def engine_rows(pair, h, st, cfg, memo=None):
    """(find_stories, current_tap) on bars cut at the last closed origin bar. With a memo dict the result is
    reused while no new origin bar has closed (same bars -> same digest -> same output), so W/M (and D within
    the day) are not recomputed every hour."""
    key = _digest(h, st, cfg) if memo is not None else None
    hit = memo.get(st) if memo is not None else None
    if hit and hit["key"] == key:
        return copy.deepcopy(hit["stories"]), copy.deepcopy(hit["tap"])
    stories, tap = find_stories(pair, h, st, cfg), current_tap(pair, h, st, cfg)
    if memo is not None:
        memo[st] = {"key": key, "stories": copy.deepcopy(stories), "tap": copy.deepcopy(tap),
                    "last_bar": str(h.index[-1]) if len(h) else None}
    return stories, tap


def pair_state(pair, h1, now, stories, cfg, memo=None):
    """All bias rows the engine sees now for one pair (closed bars only). `memo` (dict, optional) caches the
    engine output per story between runs (see engine_rows)."""
    now = _ts(now)
    h1 = drop_forming(h1, "H1", now)
    out = []
    for st in stories:
        otf = STORIES[st][0]
        h = drop_forming(h1, otf, now)
        rows = []
        found, t = engine_rows(pair, h, st, cfg, memo)
        for s in found:
            status = {"target": "TARGET_HIT", "invalidated": "INVALIDATED"}.get(s["kevin_outcome"], "CONFIRMED")
            r = to_row(s, status)
            r["_story"] = s  # raw engine story (breakout_time etc.) for the entry model; not stored
            if status == "CONFIRMED":
                ob = resample(h, otf)
                since = int((pd.to_datetime(ob["start"]) >= _ts(r["confirm_time"])).sum())
                if _beyond_target(r, h1[h1.index >= _ts(r["confirm_time"])]):
                    r["status"] = "TARGET_HIT"  # wick reached target in hours after the last closed origin bar
                elif since > cfg["max_hold"]:
                    r["status"] = "CANCELLED"   # held max_hold bars without an outcome
            rows.append(r)
        if t and not any(r["tap_time"] == _dt(t["tap_time"]) for r in rows) \
                and not any(r["status"] == "CONFIRMED" for r in rows):
            rows.append(to_row(t, "TAPPED"))
        out += rows
    return mark_mw_conflict(out, cfg)


def mark_mw_conflict(rows, cfg=None):
    """STRATEGY §2: latest CONFIRMED M and W stories point opposite ways -> D stories get no_trade=True."""
    cfg = {**DEFAULT, **(cfg or {})}
    if not cfg.get("mw_conflict_filter", True):
        return rows
    conf = lambda st: [r for r in rows if r["story"] == st and r["status"] == "CONFIRMED"]  # noqa: E731
    if mw_conflict(conf("M"), conf("W")):
        for r in rows:
            if r["story"] == "D":
                r["no_trade"] = True
                r["no_trade_reason"] = "M/W conflict"
    return rows


def state_stories(stories, cfg):
    """Stories the engine must compute: the M/W check for D stories needs M and W even when only D is
    watched (settings `stories`). Rows of the extra stories are used for the check, not stored."""
    if "D" in stories and {**DEFAULT, **(cfg or {})}.get("mw_conflict_filter", True):
        return list(stories) + [s for s in ("W", "M") if s not in stories]
    return list(stories)


def filter_alerts(alerts):
    """Drop TAPPED/CONFIRMED alerts of NO_TRADE (M/W conflict) stories; outcomes are still announced."""
    return [(ev, r) for ev, r in alerts if not (r.get("no_trade") and ev in ACTIVE)]


def _same(a, b):
    if bool(a.get("no_trade")) != bool(b.get("no_trade")):
        return False
    for k in ("status", "side", "level_kind", "confirm_time"):
        if a.get(k) != b.get(k):
            return False
    for k in ("level", "point_b", "target", "invalidation"):
        x, y = a.get(k), b.get(k)
        if (x is None) != (y is None) or (x is not None and abs(float(x) - float(y)) > 1e-9):
            return False
    return True


def reconcile(new_rows, old_rows, now, h1=None, cfg=None):
    """Compare engine rows with stored rows of one pair. Returns (rows_to_write, alerts) where alerts are
    (event, row). Pure function apart from `resolve` for stored stories that disappeared."""
    now = _ts(now).to_pydatetime().replace(tzinfo=None)
    old = {(r["story"], r["tap_time"]): r for r in old_rows}
    seen, writes, alerts = set(), [], []
    for r in new_rows:
        key = (r["story"], r["tap_time"])
        seen.add(key)
        o = old.get(key)
        if o is not None and _same(r, o):
            continue
        writes.append(r)
        if r["status"] not in ALERT_ON:
            continue
        if o is not None:
            if o["status"] != r["status"] and o["status"] in ACTIVE + (None,):
                alerts.append((r["status"], r))
        else:  # first time the bot sees it: announce only fresh events
            when = r["confirm_time"] if r["status"] == "CONFIRMED" else r["tap_time"] if r["status"] == "TAPPED" else None
            if when is not None and now - when <= ALERT_WINDOW + _bar(r):
                alerts.append((r["status"], r))
    for key, o in old.items():
        if key in seen or o["status"] not in ACTIVE or h1 is None:
            continue
        st = resolve(o, h1, now, cfg or DEFAULT)
        if st != o["status"]:
            r = {**o, "status": st}
            writes.append(r)
            if st in ("TARGET_HIT", "INVALIDATED"):
                alerts.append((st, r))
    return writes, alerts


def _bar(r):
    # a TAPPED story is stamped with the start of its origin candle: allow one candle more
    return {"D": timedelta(days=1), "W": timedelta(days=7), "M": timedelta(days=31)}[r["story"]] \
        if r["status"] == "TAPPED" else timedelta(0)


# ------------------------------------------------------------------ entries (stage 2)
ENTRY_LIVE = ("PENDING", "TRIGGERED", "MISSED")


def entry_rows(pair, h1, rows, bias_ids, cfg=None, finder=None, ecfg=None, keep_key=False):
    """Entry rows (table `entries` shape) for CONFIRMED, tradable stories. bias_ids maps (story, tap_time)
    to bias.id. cfg = story cfg, ecfg = entry cfg. `finder` defaults to slk.entry.find_entries (injectable).
    keep_key=True adds "_key" = (story, tap_time) so bias ids can be filled in later (parallel workers)."""
    if finder is None:
        from .entry import find_entries as finder
    src = [r for r in rows if r["status"] == "CONFIRMED" and not r.get("no_trade") and r.get("_story")]
    if not src:
        return []
    out = []
    for r, e in zip(src, finder(pair, h1, [r["_story"] for r in src], ecfg, cfg, sim=False)):
        if e.get("status") not in ENTRY_LIVE:
            continue
        out.append({"bias_id": bias_ids.get((r["story"], r["tap_time"])), "pair": pair, "story": r["story"],
                    "tf": e["tf"], "side": r["side"], "model": e.get("model", "continuation"), "entry": float(e["entry"]), "stop": float(e["stop"]),
                    "tp1": float(e["tp1"]), "tp2": float(e["tp2"]), "status": e["status"],
                    "stop_pips": e.get("stop_pips")})
        if keep_key:
            out[-1]["_key"] = (r["story"], r["tap_time"])
    return out


def _entry_key(e):
    return (e.get("bias_id"), e.get("tf"), e.get("side"), round(float(e["entry"]), 6))


def reconcile_entries(new, old):
    """(writes, alerts). Alert NEW when a PENDING entry first appears, TRIGGERED when it fills (first seen or
    from PENDING). Stored rows with other statuses (APPROVED/CANCELLED ...) are never downgraded."""
    old_by = {_entry_key(o): o for o in old}
    writes, alerts = [], []
    for e in new:
        o = old_by.get(_entry_key(e))
        if o is None:
            writes.append(e)
            if e["status"] in ("PENDING", "TRIGGERED"):
                alerts.append(("ENTRY_" + e["status"], e))
        elif o["status"] != e["status"] and o["status"] == "PENDING":
            writes.append({**e, "id": o.get("id")})
            if e["status"] == "TRIGGERED":
                alerts.append(("ENTRY_TRIGGERED", e))
    return writes, alerts


MODEL_NAMES = {"continuation": "Continuation", "qmr": "QMR"}


def format_entry_alert(event, e, auto_trade="off"):
    p = e["pair"]
    model = e.get("model") or "continuation"
    fp = lambda x: fmt_price(p, x)  # noqa: E731
    head = {"ENTRY_PENDING": "NEW ENTRY (pending limit)", "ENTRY_TRIGGERED": "ENTRY TRIGGERED"}.get(
        event, event.replace("ENTRY_", "ENTRY "))
    sp = e.get("stop_pips")
    if sp is None:
        sp = round(abs(e["entry"] - e["stop"]) / pip(p), 1)
    lines = [f"{p} | {e['tf']} | {e['side']} | {MODEL_NAMES.get(model, model)} | {head}",
             f"Entry {fp(e['entry'])}  Stop {fp(e['stop'])} ({sp} pips)",
             f"TP1 {fp(e['tp1'])}  TP2 {fp(e['tp2'])}"]
    if event == "ENTRY_PENDING" and str(auto_trade).lower() == "confirm":
        lines.append("Confirm in Mini App to place the order.")
    return "\n".join(lines)


# ------------------------------------------------------------------ messages
def fmt_price(pair, x):
    if x is None:
        return "-"
    return f"{x:.3f}" if pip(pair) == 0.01 else f"{x:.5f}"


def fmt_time(t):
    return "-" if t is None else pd.Timestamp(t).strftime("%Y-%m-%d %H:%M") + " UTC"


STORY_NAME = {"D": "Daily", "W": "Weekly", "M": "Monthly"}
HEAD = {"TAPPED": "TAPPED (waiting for breakout)", "CONFIRMED": "CONFIRMED", "TARGET_HIT": "TARGET HIT",
        "INVALIDATED": "INVALIDATED"}


def format_alert(event, r):
    p = r["pair"]
    fp = lambda x: fmt_price(p, x)  # noqa: E731
    lines = [f"{p} | {STORY_NAME[r['story']]} story | {r['side']} | {HEAD.get(event, event)}",
             f"Level {fp(r['level'])} ({r.get('level_kind') or '-'})  Point B {fp(r['point_b'])}",
             f"Target {fp(r['target'])}  Invalid if close {'above' if r['side'] == 'SELL' else 'below'} "
             f"{fp(r['invalidation'])}",
             f"Tap {fmt_time(r['tap_time'])}"]
    if r.get("confirm_time"):
        lines.append(f"Confirmed {fmt_time(r['confirm_time'])}")
    return "\n".join(lines)


def summary_line(pair, rows):
    act = sorted((r for r in rows if r["status"] in ACTIVE), key=lambda r: "MWD".index(r["story"]))
    if not act:
        return f"{pair}: NO_TRADE"
    conf = {r["story"]: r["side"] for r in act if r["status"] == "CONFIRMED"}
    parts = []
    for r in act:
        s = f"{r['story']} {r['side']}"
        if r["status"] == "TAPPED":
            s += " tapped"
        else:
            s += f" B {fmt_price(pair, r['point_b'])} T {fmt_price(pair, r['target'])}"
        parts.append(s)
    line = f"{pair}: " + ", ".join(parts)
    if "M" in conf and "W" in conf and conf["M"] != conf["W"]:
        line += " -> NO_TRADE (M/W disagree)"
    return line


def format_summary(now, by_pair, kill_switch="off"):
    ny = _ts(now).tz_convert("America/New_York")
    head = [f"SLK daily bias {ny:%a %Y-%m-%d} (NY close)",
            "Trading: OFF (kill switch)" if str(kill_switch).lower() == "on" else "Trading: kill switch off"]
    return "\n".join(head + [summary_line(p, rows) for p, rows in by_pair.items()])


def summary_due(now, last_sent):
    """True at the first run after 17:05 New York (not on Saturday), once per NY day."""
    ny = _ts(now).tz_convert("America/New_York")
    if ny.dayofweek == 5 or (ny.hour, ny.minute) < (17, 5):
        return False
    return last_sent != ny.strftime("%Y-%m-%d")


def send_telegram(text, token=None, chat=None):
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = chat or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[telegram off]\n" + text + "\n", flush=True)
        return False
    ok = True
    for i in range(0, len(text), 3900):
        body = urllib.parse.urlencode({"chat_id": chat, "text": text[i:i + 3900],
                                       "disable_web_page_preview": "true"}).encode()
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", body, timeout=20) as r:
                ok &= json.loads(r.read()).get("ok", False)
        except Exception as e:  # never print the URL (it holds the token)
            print(f"telegram send failed: {type(e).__name__} {getattr(e, 'code', '')}", flush=True)
            ok = False
    return ok


# ------------------------------------------------------------------ settings (DB table `settings`)
ALERT_KEY = {"TAPPED": "alert_tapped", "CONFIRMED": "alert_confirmed", "TARGET_HIT": "alert_ended",
             "INVALIDATED": "alert_ended"}


def build_cfg(stored=None, overrides=None):
    """(story cfg, entry cfg, typed settings) from stored strings (slk/settings.py schema); anything missing
    or invalid falls back to the code defaults (Kevin's rules). `overrides` (--cfg JSON) win over both."""
    vals = S.load(stored)
    cfg = {**DEFAULT, **S.story_cfg(vals), **(overrides or {})}
    ecfg = {**ENTRY_DEFAULT, **S.entry_cfg(vals)}
    return cfg, ecfg, vals


def alerts_enabled(alerts, vals):
    """Drop story alerts whose Telegram toggle is off."""
    return [(ev, r) for ev, r in alerts if vals.get(ALERT_KEY.get(ev, ""), True)]


def _load_settings(db):
    try:
        return db.get_settings()
    except Exception as e:  # settings unreadable -> code defaults
        print(f"settings read failed ({type(e).__name__}); using code defaults", flush=True)
        return {}


# ------------------------------------------------------------------ parallel engine work (no DB)
def _memo_path(pair):
    return os.path.join(candles_store.DIR, "memo", f"{pair}.pkl")


def _load_memo(pair):
    try:
        with open(_memo_path(pair), "rb") as f:  # written only by this runner into the Actions cache
            return pickle.load(f)
    except Exception:
        return {}


def _save_memo(pair, memo):
    try:
        os.makedirs(os.path.dirname(_memo_path(pair)), exist_ok=True)
        with open(_memo_path(pair) + ".tmp", "wb") as f:
            pickle.dump(memo, f)
        os.replace(_memo_path(pair) + ".tmp", _memo_path(pair))
    except OSError as e:
        print(f"memo {pair}: not saved ({e})", flush=True)


def compute_pair(job):
    """Engine work of one pair (runs in a worker process): bias rows + entry rows. No DB access."""
    pair, now, engine_stories, stories, cfg, ecfg, entries_on = job
    try:
        h1 = recent(pair, HISTORY_DAYS)
        memo = _load_memo(pair)
        rows = [r for r in pair_state(pair, h1, now, engine_stories, cfg, memo) if r["story"] in stories]
        _save_memo(pair, memo)
        ents = entry_rows(pair, drop_forming(h1, "H1", now), rows, {}, cfg, ecfg=ecfg, keep_key=True) \
            if entries_on else []
        return {"pair": pair, "rows": rows, "entries": ents}
    except Exception as e:
        return {"pair": pair, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}


def compute_all(jobs, workers=None):
    """compute_pair for every job, in a process pool (one pair per task; results in job order)."""
    workers = workers or int(os.environ.get("SLK_WORKERS", "0") or 0) or (os.cpu_count() or 1)
    if workers > 1 and len(jobs) > 1:
        try:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor
            ctx = multiprocessing.get_context("fork")
            with ProcessPoolExecutor(min(workers, len(jobs)), mp_context=ctx) as ex:
                return list(ex.map(compute_pair, jobs))
        except Exception as e:  # no fork / broken pool: do it here
            print(f"process pool unavailable ({type(e).__name__}); computing sequentially", flush=True)
    return [compute_pair(j) for j in jobs]


# ------------------------------------------------------------------ run status ("bot alive")
STATUS_EVERY = timedelta(hours=4) - timedelta(minutes=10)  # cron jitter must not skip a 4-hour slot


def status_due(mode, last_sent, now, errors=()):
    """`status_updates` setting: each_run | every_4h | off. Errors always report unless off."""
    if mode == "off":
        return False
    if mode == "each_run" or errors or not last_sent:
        return True
    try:
        return _ts(now) - _ts(last_sent) >= STATUS_EVERY
    except (TypeError, ValueError):
        return True


def format_status(now, planned, started, seconds, pairs_ok, pairs_total, active, no_trade, pending, errors,
                  note=""):
    ny = _ts(now).tz_convert("America/New_York")
    late = int((_ts(started) - _ts(planned)).total_seconds() // 60)
    lines = [f"SLK bot alive - {_ts(now):%Y-%m-%d %H:%M} UTC ({ny:%a %H:%M} NY)",
             f"Pairs checked: {pairs_ok}/{pairs_total}",
             f"Active biases: {active}" + (f" ({no_trade} NO_TRADE)" if no_trade else ""),
             f"Pending entries: {'-' if pending is None else pending}",
             f"Start delay: {late} min (planned {_ts(planned):%H:%M} UTC)",
             f"Run time: {seconds:.0f} s"]
    if note:
        lines.append(note)
    lines.append("Errors: none" if not errors else f"Errors ({len(errors)}): " + " | ".join(errors)[:1500])
    return "\n".join(lines)


def weekend_close_day(now):
    """NY date (YYYY-MM-DD) of the Friday close of the current FX weekend, or None while the market is open."""
    if not candles_store.fx_closed(now):
        return None
    ny = _ts(now).tz_convert("America/New_York")
    return (ny - pd.Timedelta(days=(ny.dayofweek - 4) % 7)).strftime("%Y-%m-%d")


# ------------------------------------------------------------------ main
def planned_time(now, event):
    """The cron slot (minute 7 of the hour) this run belongs to; for manual runs = start time."""
    if event != "schedule":
        return now
    slot = now.replace(minute=7, second=0, microsecond=0)
    return slot if now >= slot else slot - timedelta(hours=1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="")
    ap.add_argument("--stories", default="")
    ap.add_argument("--dry-run", action="store_true", help="no DB, no Telegram; print results")
    ap.add_argument("--cfg", default="{}", help="JSON overrides of story.DEFAULT")
    a = ap.parse_args(argv)
    overrides = json.loads(a.cfg)
    cfg, ecfg, vals = build_cfg({}, overrides)
    started = datetime.now(timezone.utc).replace(microsecond=0)
    t0 = time.monotonic()
    naive = lambda t: t.replace(tzinfo=None)  # noqa: E731

    if a.dry_run:
        pairs = a.pairs.split(",") if a.pairs else list(PAIRS)
        stories = (a.stories or "D,W,M").split(",")
        for p, err in prepare_candles(pairs, started).items():
            print(f"{p}: download failed: {err}")
        res = compute_all([(p, started, state_stories(stories, cfg), stories, cfg, ecfg, True) for p in pairs])
        for r in res:
            if "error" in r:
                print(f"{r['pair']}: {r['error']}")
                continue
            for row in r["rows"]:
                if row["status"] in ACTIVE and not (row.get("no_trade") and row["story"] == "D"):
                    print(format_alert(row["status"], row) + "\n")
            for e in r["entries"]:
                print(format_entry_alert("ENTRY_" + e["status"], e) + "\n")
            print(summary_line(r["pair"], r["rows"]))
        print(f"dry run: {len(pairs)} pairs in {time.monotonic() - t0:.1f} s")
        return 0

    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is not set: add the GitHub secrets DATABASE_URL, TELEGRAM_BOT_TOKEN and "
              "TELEGRAM_CHAT_ID (Settings > Secrets and variables > Actions). Nothing to do, exiting OK.")
        return 0
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set: alerts will only be printed in the log.")

    from . import db
    db.apply_schema()
    event = os.environ.get("GITHUB_EVENT_NAME", "manual")
    planned = planned_time(started, event)
    run_id = db.start_run(JOB, naive(planned), naive(started))
    print(f"run {run_id}: planned {planned:%H:%M} started {started:%H:%M:%S} UTC "
          f"(late {int((started - planned).total_seconds() // 60)} min)", flush=True)

    errors, sent, by_pair, pairs, note = [], 0, {}, [], ""
    try:
        cfg, ecfg, vals = build_cfg(_load_settings(db), overrides)  # re-read every run
        pairs = [p.strip().upper() for p in a.pairs.split(",") if p.strip()] if a.pairs else (vals["pairs"] or list(PAIRS))
        stories = [s.strip().upper() for s in a.stories.split(",") if s.strip().upper() in STORIES] if a.stories \
            else [s for s in vals["stories"] if s in STORIES]
        kill = "on" if vals["kill_switch"] == "on" else "off"
        auto = vals["auto_trade"]
        weekend = weekend_close_day(started)
        if weekend and event == "schedule" and db.get_setting("weekend_done") == weekend:
            # FX closed and the final run after the Friday close (bars + daily summary) is done: nothing can change
            note = f"weekend: market closed since {weekend} 17:00 NY, skipped"
            print(note)
            db.finish_run(run_id, True, note)
            return 0

        t_dl = time.monotonic()
        dl_err = prepare_candles(pairs, started)
        errors += [f"{p}: download: {e}" for p, e in dl_err.items()]
        now = datetime.now(timezone.utc)
        t_cpu = time.monotonic()
        todo = [p for p in pairs if p not in dl_err]
        results = compute_all([(p, now, state_stories(stories, cfg), stories, cfg, ecfg,
                                vals["continuation_entries"]) for p in todo])
        t_db = time.monotonic()
        for res in results:
            p = res["pair"]
            if "error" in res:
                errors.append(f"{p}: {res['error']}")
                print(res.get("trace", ""), flush=True)
                continue
            try:
                h1 = recent(p, HISTORY_DAYS)
                new = res["rows"]
                old = [r for r in db.get_bias(p) if r["story"] in stories]
                writes, alerts = reconcile(new, old, now, h1, cfg)
                for r in writes:
                    db.upsert_bias(r)
                for ev, r in alerts_enabled(filter_alerts(alerts), vals):
                    sent += send_telegram(format_alert(ev, r))
                by_pair[p] = [r for r in db.get_bias(p) if r["story"] in stories]
                ids = {(r["story"], r["tap_time"]): r.get("id") for r in by_pair[p]}
                ents = res["entries"]
                for e in ents:
                    e["bias_id"] = ids.get(e.pop("_key", None))
                ew, ea = reconcile_entries(ents, db.get_entries(p)) if vals["continuation_entries"] else ([], [])
                for e in ew:
                    db.upsert_entry(e)
                for ev, e in ea if vals["alert_entry"] else []:
                    sent += send_telegram(format_entry_alert(ev, e, auto))
                print(f"{p}: {len(new)} stories, {len(writes)} written, {len(alerts)} alerts, "
                      f"{len(ew)} entries written", flush=True)
            except Exception as e:  # one bad pair must not stop the others
                errors.append(f"{p}: {type(e).__name__}: {e}")
                traceback.print_exc()
        print(f"timing: download {t_cpu - t_dl:.1f}s, engine {t_db - t_cpu:.1f}s, db+alerts "
              f"{time.monotonic() - t_db:.1f}s", flush=True)
        if by_pair and vals["daily_summary"] and summary_due(started, db.get_setting("last_summary")):
            if send_telegram(format_summary(started, by_pair, kill)) or not os.environ.get("TELEGRAM_BOT_TOKEN"):
                db.set_setting("last_summary", _ts(started).tz_convert("America/New_York").strftime("%Y-%m-%d"))
        if weekend and by_pair and not errors:
            db.set_setting("weekend_done", weekend)
            note = "Market closed: this was the last run until Sunday 17:00 NY."
    except Exception as e:
        errors.append(f"fatal: {type(e).__name__}: {e}")
        traceback.print_exc()
    secs = time.monotonic() - t0
    try:
        mode = vals.get("status_updates", "every_4h")
        if status_due(mode, db.get_setting("last_status"), started, errors):
            rows = [r for rs in by_pair.values() for r in rs if r["status"] in ACTIVE]
            try:
                pending = db.count_entries("PENDING")
            except Exception:
                pending = None
            text = format_status(datetime.now(timezone.utc), planned, started, secs, len(by_pair), len(pairs),
                                 len(rows), sum(1 for r in rows if r.get("no_trade")), pending, errors, note)
            if send_telegram(text) or not os.environ.get("TELEGRAM_BOT_TOKEN"):
                db.set_setting("last_status", _ts(started).isoformat())
    except Exception as e:
        print(f"status message failed: {type(e).__name__}", flush=True)
    run_note = f"pairs ok {len(by_pair)}, alerts {sent}, {secs:.0f}s" + ("; " + " | ".join(errors) if errors else "")
    db.finish_run(run_id, not errors, run_note)
    print(run_note)
    return 1 if errors and not by_pair else 0  # red only when nothing worked


if __name__ == "__main__":
    sys.exit(main())
