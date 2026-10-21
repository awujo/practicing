"""Live bias runner (GitHub Actions, hourly). STRATEGY §2, CONTRACT.md.

For every pair: download recent H1 candles, drop still-forming bars, run the story line for D/W/M,
add the current TAPPED (not yet confirmed) story, sync table `bias`, and send Telegram alerts when a story is
newly TAPPED / CONFIRMED or ends (TARGET_HIT / INVALIDATED). Entries of CONFIRMED stories go to table `entries`;
filled ones are paper-tracked on closed H1 bars (TP1_HIT / TP2_HIT / SL_HIT / EXPIRED, alert once). Once a day
(first run after 17:05 New York) a summary with one line per pair.

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

from . import instruments
from . import settings as S
from . import store as candles_store
from .backtest import PAIRS
from .candles import _key, nominal_end, resample
from .structure import pivots
from .entry import DEFAULT as ENTRY_DEFAULT
from . import standing
from .story import DEFAULT, STORIES, tf_trend, current_tap, find_stories, mw_conflict, pip

JOB = "live"
HISTORY_DAYS = 3 * 365 + 30       # enough months for M/W stories
ALERT_WINDOW = timedelta(hours=36)  # a story first seen by the bot is announced only if this fresh
ACTIVE = ("TAPPED", "CONFIRMED")
ALERT_ON = ("TAPPED", "CONFIRMED", "TARGET_HIT", "INVALIDATED", "ENDED_FLIP")
ENDED_AFTER_CONF = ("TARGET_HIT", "INVALIDATED", "ENDED_FLIP", "CANCELLED")
STATUS_OF = {"target": "TARGET_HIT", "invalidated": "INVALIDATED", "ended_flip": "ENDED_FLIP"}  # engine -> bias
BAR_LEN = {"H1": pd.Timedelta(hours=1), "H4": pd.Timedelta(hours=4), "D": pd.Timedelta(days=1),
           "W": pd.Timedelta(days=5)}  # a week closes Friday 17:00 New York (shifted Saturday 00:00)


# ------------------------------------------------------------------ candles
def recent(pair, days):
    """Engine candles of one pair from the candle store (slk/store.py); tests replace this."""
    return candles_store.recent(pair, days)


def prepare_candles(pairs, now):
    """Bring every pair's store up to the last closed hour: IC Markets cTrader over one connection (only the last
    few days are fetched when the store is current), Dukascopy for pairs where cTrader fails (a ::warning::
    annotation says so). The connection is closed before the engine's process pool forks. Returns {pair: error}."""
    try:
        return candles_store.update_all(pairs, now, days=HISTORY_DAYS)
    finally:
        candles_store.close_feed()


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
    now_shift = now.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
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


def _flag(x):
    """bool / 0/1 from the DB / None -> True, False or None."""
    return None if x is None or (isinstance(x, float) and pd.isna(x)) else bool(int(x))


def to_row(s, status):
    """Bias row (table `bias` columns, see slk/db.BIAS_COLS) plus alert-only labels (level_time, trend,
    htf_trend), which are not stored."""
    return {"pair": s["pair"], "story": s["story"], "side": s["side"], "status": status,
            "level_kind": s.get("level_kind"), "level": float(s["level"]),
            "point_b": None if s.get("B") is None else float(s["B"]),
            "target": None if s.get("target") is None else float(s["target"]),
            "invalidation": float(s["level"]), "tap_time": _dt(s["tap_time"]),
            "confirm_time": _dt(s.get("confirm_time")), "rule": s.get("rule") or "standard",
            "end_reason": s.get("end_reason") if status not in ACTIVE else None,
            "breakout_time": _dt(s.get("breakout_time")), "next_day": _flag(s.get("next_day")),
            "retrace": _flag(s.get("retrace")), "level_time": _dt(s.get("level_time")),
            "trend": s.get("trend"), "htf_trend": s.get("htf_trend"),
            "_initial_target": s.get("initial_target"), "_preconfirm_extreme": s.get("preconfirm_extreme"),
            "level_src": s.get("level_src"), "level_candle": _dt(s.get("level_candle")),
            "chain": chain(s["story"], s["side"], s.get("htf_trend"))}


def chain(story, side, htf_trend):
    """Timeframes in line for the header: 'D1→H4', or 'W1→D1→H4' when the higher TF (W for a D story) trends the
    same way as the story (owner request 2026-10-15)."""
    otf, ctf = STORIES[story]
    tfs = [TF_LABEL[otf], TF_LABEL[ctf]]
    h = HIGHER_TF.get(story)
    if h in TF_LABEL and htf_trend == ("down" if side == "SELL" else "up"):
        tfs.insert(0, TF_LABEL[h])
    return "\u2192".join(tfs)


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
                                       ("story.py", "levels.py", "structure.py", "candles.py",
                                        "instruments.py"))).hexdigest()


def _digest(h, story, cfg, pair=""):
    """Fingerprint of everything find_stories/current_tap see: engine code, story, the pair's pip size, cfg and the
    closed bars."""
    m = hashlib.sha1(f"{ENGINE_VERSION}|{story}|{instruments.pip(pair) if pair else ''}|"
                     f"{json.dumps(cfg, sort_keys=True, default=str)}".encode())
    m.update(h.index.asi8.tobytes())
    m.update(str(h.index.dtype).encode())
    m.update(np.ascontiguousarray(h[["open", "high", "low", "close"]].to_numpy(float)).tobytes())
    return m.hexdigest()


def engine_rows(pair, h, st, cfg, memo=None):
    """(find_stories, current_tap) on bars cut at the last closed origin bar. With a memo dict the result is
    reused while no new origin bar has closed (same bars -> same digest -> same output), so W/M (and D within
    the day) are not recomputed every hour."""
    key = _digest(h, st, cfg, pair) if memo is not None else None
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
        rows, cb = [], None
        found, t = engine_rows(pair, h, st, cfg, memo)
        for s in found:
            status = STATUS_OF.get(s["kevin_outcome"], "CONFIRMED")
            r = to_row(s, status)
            r["_story"] = s  # raw engine story (breakout_time etc.) for the entry model; not stored
            if s.get("erl_taken") and cfg.get("erl_taken_no_trade", True):
                # owner 2026-10-16 + backtest: a wick took the target (external range liquidity) before the
                # confirmation -> trading it is late (variant target_unswept=skip: -80R vs -110R). Bias kept.
                r["no_trade"], r["no_trade_reason"] = True, ERL_TAKEN
            if status == "CONFIRMED":
                ob = resample(h, otf)
                since = int((pd.to_datetime(ob["start"]) >= _ts(r["confirm_time"])).sum())
                if _beyond_target(r, h1[h1.index >= _ts(r["confirm_time"])]):
                    r["status"] = "TARGET_HIT"  # wick reached target in hours after the last closed origin bar
                    r["end_reason"] = f"target {r['target']} reached"
                elif since > cfg["max_hold"]:
                    r["status"] = "CANCELLED"   # held max_hold bars without an outcome
                    r["end_reason"] = f"no outcome within {cfg['max_hold']} {otf} bars"
            if r.get("breakout_time") is not None and status in ("CONFIRMED", "TARGET_HIT", "INVALIDATED",
                                                                  "ENDED_FLIP", "CANCELLED") \
                    and now - _ts(r["breakout_time"]) <= timedelta(days=CONT_DAYS):
                if cb is None:
                    cb = resample(drop_forming(h1, STORIES[st][1], now), STORIES[st][1])
                until = s.get("end_time")
                if cfg.get("close_at_target"):
                    r["_closed_at_target"] = r["status"] == "TARGET_HIT"  # alert text; not stored
                elif r["status"] in AFTER_TARGET and r.get("confirm_time"):
                    # owner 2026-10-16: after the target the question is what comes next, the story line ended
                    # (origin close back through the level) or a new internal break that continues it
                    r["_end_time"] = s.get("end_time") or _target_time(r, h1)
                    r["line_end"] = line_end(r, resample(h, otf))
                    until = r["line_end"]
                r["cont_breaks"] = pack_breaks(continuation_breaks(r, cb, cfg, until))
            rows.append(r)
        if t and not any(r["tap_time"] == _dt(t["tap_time"]) for r in rows) \
                and not any(r["status"] == "CONFIRMED" for r in rows):
            r = to_row(t, "TAPPED")
            eb = early_breakout(r, h1, h, now)
            if eb:
                r["_early"] = eb  # not stored; slk.live.early_alerts sends it once (setting early_breakout_alert)
            rows.append(r)
        out += rows
    return mark_htf_bias(mark_mw_conflict(out, cfg), cfg)


ERL_TAKEN = "external liquidity already taken before the confirmation"
CONT_DAYS = 60  # continuation breaks are tracked for stories that broke out in the last 60 days
AFTER_TARGET = ("TARGET_HIT", "CANCELLED")  # the bias stands after these (slk.standing.KEEPS) until the line ends


def _target_time(r, h1):
    """Start of the first H1 bar after the confirmation whose wick reached the target (live TARGET_HIT)."""
    if r.get("target") is None:
        return None
    b = h1[h1.index >= _ts(r["confirm_time"])]
    hit = b[(b["low"] <= r["target"]) if r["side"] == "SELL" else (b["high"] >= r["target"])]
    return _dt(hit.index[0]) if len(hit) else None


def line_end(r, ob):
    """Start of the first closed origin candle (D for a D story) after the confirmation that closed back through
    the key level: the story line is over after its target (Kevin: "we are still bullish on weekly ... because we
    are not close below this body" [T all-in-1@1249-1290]). None while the line holds. `ob` = closed origin bars."""
    after = ob[pd.to_datetime(ob["start"]) >= _ts(r["confirm_time"])]
    hit = after[(after["close"] > r["level"]) if r["side"] == "SELL" else (after["close"] < r["level"])]
    return _dt(hit["start"].iloc[0]) if len(hit) else None


def pack_breaks(br):
    """continuation_breaks -> stored text 'level@YYYY-MM-DD HH:MM[@n@first]; ...' (column bias.cont_breaks), None
    if empty. n/first = how many V's (A's) one candle cleared and the nearest of them, when more than one."""
    return ";".join(f"{b['level']:.6g}@{pd.Timestamp(b['time']):%Y-%m-%d %H:%M}"
                    + (f"@{b['n']}@{b['first']:.6g}" if b.get("n", 1) > 1 else "") for b in br) or None


def unpack_breaks(txt):
    out = []
    for part in str(txt or "").split(";"):
        if "@" in part:
            f = part.split("@")
            b = {"level": float(f[0]), "time": f[1]}
            if len(f) >= 4:
                b.update(n=int(f[2]), first=float(f[3]))
            out.append(b)
    return out


def continuation_breaks(r, cb, cfg, until=None):
    """Owner 2026-10-16 (EURCHF chart: white line = external break of point B, yellow lines = the next breaks):
    after the external break, each confirm-TF close (H4 for a D story) through the next intact close-line V-shape
    (A-shape for a buy) beyond point B = a continuation break in the bias direction.
    After the target the line goes on (owner 2026-10-16; Kevin: "if price takes out the internal range liquidity, we
    will have the next target, external range liquidity" [T liquidity-pt2@584-599]): V's beyond the target count too,
    until `until` (the line end). `cb` = confirm-TF bars (resample of closed H1). Returns [{"level" (furthest V the
    candle closed through), "first" (nearest), "n" (how many), "time" (breaking candle start), "close"}] in time
    order, one per candle. The V's are the order-`b_pivot` close-line turns
    (the same as point B), known before the breaking candle closed (no look-ahead)."""
    if r.get("breakout_time") is None or r.get("point_b") is None or r.get("target") is None or cb.empty:
        return []
    sell = r["side"] == "SELL"
    B = float(r["point_b"])
    start = pd.to_datetime(cb["start"])
    k0 = int(np.searchsorted(start, _ts(r["breakout_time"]), "left"))
    kend = len(cb) if until is None else int(np.searchsorted(start, _ts(until), "right"))
    close = cb["close"].to_numpy()
    lo = max(0, k0 - 120)  # V's formed in the 120 bars (20 days of H4) before the break are enough
    piv = [p for p in pivots(close[lo:kend], cfg["b_pivot"]) if p[1] == ("L" if sell else "H")]
    piv = [(p[0] + lo, p[2], p[3] + lo) for p in piv if ((p[2] < B) if sell else (p[2] > B))]
    out, used = [], set()
    for k in range(k0 + 1, kend):
        hit = []
        for i, price, known in piv:
            if i in used or known >= k:
                continue
            seg = close[i + 1:k]  # intact: no close through it since it formed
            if len(seg) and ((seg < price).any() if sell else (seg > price).any()):
                used.add(i)
                continue
            if (close[k] < price) if sell else (close[k] > price):
                used.add(i)
                hit.append(float(price))
        if hit:
            # one candle clearing several V's is one break (Kevin: "it is one candle that took out both the
            # internal and external range liquidity" [T liquidity-pt2@919-947]); owner 2026-10-16 NZDJPY: four lines
            # for one H4 close read as a repeat
            hit.sort(reverse=sell)
            out.append({"level": hit[-1], "first": hit[0], "n": len(hit), "time": _dt(start[k]),
                        "close": float(close[k])})
    return out


def early_breakout(r, h1, h, now):
    """Early (unconfirmed) breakout of a TAPPED story: a CLOSED confirm-TF candle (H4 for a D story) inside the
    still-open origin candle closed beyond point B. `h1` = closed H1 bars, `h` = bars cut at the last closed origin
    candle (what the engine saw). The origin close beyond B is still pending (same_bar_close, Kevin qns-pt2@1860-1930),
    so this is never a confirmation. Returns {"time": confirm-TF candle start, "close": its close} or None."""
    if r.get("point_b") is None or h.empty:
        return None
    ctf = STORIES[r["story"]][1]
    tail = drop_forming(h1[h1.index > h.index[-1]], ctf, now)  # hours of the open origin candle, closed ctf bars
    if tail.empty:
        return None
    cb = resample(tail, ctf)
    sell = r["side"] == "SELL"
    hit = cb[(cb["close"] < r["point_b"]) if sell else (cb["close"] > r["point_b"])]
    if hit.empty:
        return None
    return {"time": _dt(hit["start"].iloc[0]), "close": float(hit["close"].iloc[0])}


def early_key(r):
    return f"{r['pair']}|{r['story']}|{pd.Timestamp(r['tap_time']):%Y-%m-%d %H:%M}"


def early_alerts(rows, sent, now, keep_days=40):
    """(alerts [("BREAKOUT", row)], updated sent dict). `sent` = {early_key: ISO time sent} from settings key
    `early_alerts_sent`: one early alert per story, ever; entries older than keep_days are dropped. Only TAPPED,
    tradable rows; the row keeps status TAPPED (an early alert never becomes or replaces CONFIRMED)."""
    now = _ts(now)
    sent = {k: v for k, v in (sent or {}).items() if _sent_age_ok(v, now, keep_days)}
    out = []
    for r in rows:
        if r.get("_early") and r["status"] == "TAPPED" and not r.get("no_trade"):
            k = early_key(r)
            if k not in sent:
                out.append(("BREAKOUT", r))
                sent[k] = now.isoformat()
    return out, sent


def _sent_age_ok(v, now, keep_days):
    try:
        return now - _ts(v) <= timedelta(days=keep_days)
    except (TypeError, ValueError):
        return False


def mark_mw_conflict(rows, cfg=None):
    """STRATEGY §2: latest CONFIRMED M and W stories point opposite ways -> D stories get no_trade=True."""
    cfg = {**DEFAULT, **(cfg or {})}
    if not cfg.get("mw_conflict_filter", True) or not cfg.get("use_monthly", True):
        return rows
    conf = lambda st: [r for r in rows if r["story"] == st and r["status"] == "CONFIRMED"]  # noqa: E731
    if mw_conflict(conf("M"), conf("W")):
        for r in rows:
            if r["story"] == "D":
                r["no_trade"] = True
                r["no_trade_reason"] = "M/W conflict"
    return rows


def _as_of(rows, t):
    """Rows as they stood at time t: stories confirmed by then, status kept only if it was already known."""
    return [r for r in rows if r.get("confirm_time") is not None and r["confirm_time"] <= t]


def mark_htf_bias(rows, cfg=None):
    """Owner 2026-10-15 + Kevin weekly-recap@622-646: a D story against the standing W bias (W story against M) is
    NO_TRADE ('against W bias'), when the setting htf_bias_filter is on (default off: a D->H4 move against the W
    bias can be the retracement that continues the W story line). Bias as of the story's confirmation. The chain
    label (W1->D1->H4) stays the higher-TF STRUCTURE trend (Kevin's alignment = BOS on W, D, H4)."""
    cfg = {**DEFAULT, **(cfg or {})}
    for r in rows:
        h = HIGHER_TF.get(r["story"])
        hr = [x for x in rows if x["story"] == h]
        if not hr:
            continue
        t = r.get("confirm_time") or r["tap_time"]
        b = standing.standing(_as_of(hr, t), h, close_at_target=cfg.get("close_at_target", False))
        if not b["side"]:
            continue
        if cfg.get("htf_bias_filter") and b["side"] != r["side"] and not r.get("no_trade"):
            r["no_trade"] = True
            r["no_trade_reason"] = f"against {h} bias ({standing.WORD[b['side']]})"
    return rows


def state_stories(stories, cfg):
    """Stories the engine must compute: the M/W check for D stories needs M and W even when only D is
    watched (settings `stories`). Rows of the extra stories are used for the check, not stored."""
    c = {**DEFAULT, **(cfg or {})}
    need = set(stories)
    if "D" in stories and c.get("mw_conflict_filter", True) and c.get("use_monthly", True):
        need |= {"W", "M"}
    need |= {HIGHER_TF[s] for s in stories if HIGHER_TF.get(s) in STORIES}  # chain label / htf_bias_filter
    if not c.get("use_monthly", True):
        need.discard("M")  # M unticked: the monthly plays no part
    return list(stories) + [s for s in ("W", "M") if s in need and s not in stories]


def filter_alerts(alerts):
    """Drop TAPPED/CONFIRMED alerts of NO_TRADE (M/W conflict) stories; outcomes are still announced."""
    return [(ev, r) for ev, r in alerts
            if not (r.get("no_trade") and ev in ACTIVE and r.get("no_trade_reason") != ERL_TAKEN)]


def _same(a, b):
    if bool(a.get("no_trade")) != bool(b.get("no_trade")):
        return False
    for k in ("status", "side", "level_kind", "confirm_time", "rule", "end_reason", "breakout_time", "level_src",
              "level_candle", "chain", "trend", "cont_breaks", "line_end"):
        if a.get(k) != b.get(k):
            return False
    for k in ("next_day", "retrace"):
        if _flag(a.get(k)) != _flag(b.get(k)):
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
                if o["status"] != "CONFIRMED" and r["status"] in ENDED_AFTER_CONF and r.get("confirm_time"):
                    # confirmed and already over between two runs: announce the confirmation first (owner
                    # 2026-10-16 EURCHF: only "TARGET HIT" arrived, never "CONFIRMED")
                    alerts.append(("CONFIRMED", {**r, "status": "CONFIRMED", "_late": True}))
                alerts.append((r["status"], r))
            elif r["status"] == "CONFIRMED" and _flag(r.get("retrace")) and _flag(o.get("retrace")) is False:
                alerts.append(("RETRACE", r))  # flag only: the story stays CONFIRMED
            if r["status"] in AFTER_TARGET and r["status"] == o["status"] and r.get("line_end") \
                    and not o.get("line_end") \
                    and _ts(now) - (_ts(r["line_end"]) + {**BAR_LEN, "M": pd.Timedelta(days=31)}[STORIES[r["story"]][0]]) \
                    <= ALERT_WINDOW:
                alerts.append(("LINE_END", r))  # the story line ended after its target: no standing bias
            elif r["status"] in ("CONFIRMED",) + (() if r.get("_closed_at_target") is not None else AFTER_TARGET) \
                    and r["status"] == o["status"]:
                # new continuation breaks after the confirmation (and after the target), announced while fresh
                # (no burst of old ones)
                seen_b = {(b["level"], b["time"]) for b in unpack_breaks(o.get("cont_breaks"))}
                ctf = BAR_LEN.get(STORIES[r["story"]][1], timedelta(hours=4))
                new_b = [b for b in unpack_breaks(r.get("cont_breaks")) if (b["level"], b["time"]) not in seen_b
                         and _ts(b["time"]) >= _ts(r["confirm_time"])
                         and _ts(now) - (_ts(b["time"]) + ctf) <= ALERT_WINDOW]
                if new_b:
                    alerts.append(("CONTINUATION", {**r, "_new_breaks": new_b}))
        else:  # first time the bot sees it: announce only fresh events
            when = r["confirm_time"] if r["status"] == "CONFIRMED" else r["tap_time"] if r["status"] == "TAPPED" else None
            if when is not None and now - when <= ALERT_WINDOW + _bar(r):
                alerts.append((r["status"], r))
    for key, o in old.items():
        if key in seen or o["status"] not in ACTIVE or h1 is None:
            continue
        st = resolve(o, h1, now, cfg or DEFAULT)
        r = None
        if st == "CONFIRMED" and len(h1) and _ts(h1.index[0]) < _ts(o["tap_time"]) - timedelta(days=400):
            # the engine sees this story's whole history and no longer reports it: the rules or settings changed
            # (e.g. flip_max_age dropped its level). Close it quietly instead of leaving it CONFIRMED for ever.
            r = {**o, "status": "CANCELLED", "end_reason": standing.DROPPED}
        elif st != o["status"]:
            r = {**o, "status": st}
        if r is not None:
            writes.append(r)
            if st in ("TARGET_HIT", "INVALIDATED"):
                alerts.append((st, r))
    return writes, _one_continuation(alerts)


def _one_continuation(alerts):
    """Several stories of one story TF (an older one past its target and the current one) see the same H4 break:
    announce it once, on the latest confirmed story (the one holding the bias)."""
    cont = [(i, r) for i, (ev, r) in enumerate(alerts) if ev == "CONTINUATION"]
    drop, seen = set(), set()
    for i, r in sorted(cont, key=lambda x: _ts(x[1]["confirm_time"]), reverse=True):
        keys = {(r["story"], r["side"], b["time"]) for b in r["_new_breaks"]}
        if keys <= seen:
            drop.add(i)
        seen |= keys
    return [a for i, a in enumerate(alerts) if i not in drop]


def bias_notes(alerts, old, writes, trends=None, close_at_target=False):
    """Adds r['_bias_note'] (slk.standing.note) to each alert: continuation / BIAS CHANGE / bias stays after the
    target / no bias after an invalidation. old = stored rows before this run, writes = rows written now."""
    after = {(r["story"], r["tap_time"]): r for r in old}
    after.update({(r["story"], r["tap_time"]): r for r in writes})
    after = list(after.values())
    for ev, r in alerts:
        # bias before this event: every other story as it stands now (a continuation sees the earlier ones)
        t = (trends or {}).get(r["story"])
        before = standing.standing([x for x in after if x["tap_time"] != r["tap_time"]], r["story"], t, close_at_target)
        r["_bias_note"] = standing.note(ev, r, before, standing.standing(after, r["story"], t, close_at_target))
    return alerts


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
                    "stop_pips": e.get("stop_pips"),
                    "filled_at": _dt(e.get("fill_time")) if e["status"] == "TRIGGERED" else None})
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
        elif o["status"] == e["status"] == "TRIGGERED" and o.get("filled_at") is None and e.get("filled_at"):
            writes.append({**e, "id": o.get("id")})  # filled before fill times were stored: add it for tracking
    return writes, alerts


# ------------------------------------------------------------------ paper outcome of filled entries
BIAS_ENDED = ("TARGET_HIT", "INVALIDATED", "ENDED_FLIP", "CANCELLED")


def cancel_entries(stored, bias_status):
    """PENDING entries whose story has ended (bias row TARGET_HIT / INVALIDATED / ENDED_FLIP / CANCELLED) before
    the fill -> CANCELLED. Same rule as slk.entry (`story_end`: no fill after the story's end); the engine no longer
    computes entries for ended stories, so without this they would stay PENDING. APPROVED rows are left alone."""
    return [(e, {"status": "CANCELLED"}) for e in stored
            if e.get("status") == "PENDING" and bias_status.get(e.get("bias_id")) in BIAS_ENDED]


def track_entries(stored, h1, ecfg=None):
    """Paper tracking (bot signals, no broker) of stored filled entries on CLOSED H1 bars `h1` (the caller drops the
    forming hour). Only rows still open are tracked: TRIGGERED with filled_at, and TP1_HIT not yet closed. Returns
    [(row, fields, events)]: fields for db.update_entry_result, events = new TP1 / TP2 / SL / SL_AFTER_TP1 alerts
    (events already implied by the stored status are dropped, so nothing is announced twice)."""
    from .entry import paper_track
    out = []
    for e in stored:
        if e.get("closed_at") is not None or e.get("status") not in ("TRIGGERED", "TP1_HIT") or not e.get("filled_at"):
            continue
        t = paper_track(e, h1, ecfg)
        if t is None or t["status"] == "TRIGGERED":
            continue
        if t["status"] == e["status"] and t["closed_at"] is None:
            continue  # TP1_HIT, TP2 leg still open: nothing new
        done = {"TP1"} if e["status"] == "TP1_HIT" else set()
        fields = {k: t[k] for k in ("status", "result_r", "result_r_tp2", "hit_price", "closed_at")}
        out.append((e, fields, [ev for ev in t["events"] if ev not in done]))
    return out


RESULT_HEAD = {"TP1": "\u2705 TP1 hit", "TP2": "\u2705 TP2 hit", "SL": "\u274c Stop hit",
               "SL_AFTER_TP1": "\u274c Stop hit after TP1"}


def fmt_r(r):
    """+1.6R / -1R / +0.25R."""
    return f"{float(r):+.2f}".rstrip("0").rstrip(".") + "R"


def format_result_alert(event, e, fields):
    """'✅ TP1 hit · EURUSD H4 BUY · +1.6R' (+ model and a paper-result line)."""
    r = {"TP1": fields.get("result_r"), "TP2": fields.get("result_r_tp2"), "SL": -1.0,
         "SL_AFTER_TP1": -1.0}[event]
    tail = fmt_r(r)
    if event == "SL_AFTER_TP1":
        tail = f"{fmt_r(-1)} on the TP2 leg (TP1 {fmt_r(fields.get('result_r') or e.get('result_r') or 0)} kept)"
    model = MODEL_NAMES.get(e.get("model") or "continuation", e.get("model"))
    return "\n".join([f"{RESULT_HEAD[event]} \u00b7 {e['pair']} {e.get('tf') or ''} {e.get('side') or ''} \u00b7 {tail}",
                      f"{model} \u00b7 entry {fmt_price(e['pair'], e['entry'])} \u00b7 paper result (signal), not a broker trade"])


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
    """Price with the symbol's decimals: FX 5, JPY 3, XAUUSD 2, XAGUSD 3, indices 2 (cTrader digits when known)."""
    return instruments.fmt(pair, x)


CLOCK = lambda: pd.Timestamp.now(tz="UTC")  # noqa: E731  (tests pin it)


def rel_day(x, now):
    """Owner request 2026-10-15: 'Today' / 'Yesterday' / 'Tomorrow' / 'Monday' (this week) / 'Last week Monday',
    None further away. x and now are tz-aware in the same zone; weeks start on Monday."""
    d = (x.normalize() - now.normalize()).days
    if d == 0:
        return "Today"
    if d == -1:
        return "Yesterday"
    if d == 1:
        return "Tomorrow"
    week = lambda y: (y.normalize() - pd.Timedelta(days=y.dayofweek))  # noqa: E731
    w = (week(x) - week(now)).days // 7
    if w == 0:
        return f"{x:%A}"
    if w == -1:
        return f"Last week {x:%A}"
    if w == 1:
        return f"Next week {x:%A}"
    return None


def fmt_time(t, tz=None, now=None):
    """'2026-10-12 21:00 UTC' (tz None), else in that IANA zone with a friendly day when it is near:
    'Today, Mon 12 Oct 22:00 WAT', 'Last week Monday, 5 Oct 22:00 WAT', far away 'Mon 21 Sep 22:00 WAT'
    (year added when it is not the current year)."""
    if t is None:
        return "-"
    if not tz:
        return pd.Timestamp(t).strftime("%Y-%m-%d %H:%M") + " UTC"
    x = _ts(t).tz_convert(tz)
    now = _ts(now if now is not None else CLOCK()).tz_convert(tz)
    yr = f" {x.year}" if x.year != now.year else ""
    rel = rel_day(x, now)
    if rel is None:
        return f"{x:%a} {x.day} {x:%b}{yr} {x:%H:%M} {x.tzname()}"
    if rel in ("Today", "Yesterday", "Tomorrow"):
        return f"{rel}, {x:%a} {x.day} {x:%b %H:%M} {x.tzname()}"
    return f"{rel}, {x.day} {x:%b}{yr} {x:%H:%M} {x.tzname()}"


DISPLAY_TZ = S.DEFAULTS["display_tz"]
TF_LABEL = {"M": "MN1", "W": "W1", "D": "D1", "H4": "H4", "H2": "H2", "H1": "H1"}
STORY_NAME = {"D": "Daily", "W": "Weekly", "M": "Monthly"}
HEAD = {"TAPPED": "TAPPED (waiting for breakout)", "CONFIRMED": "CONFIRMED", "TARGET_HIT": "TARGET HIT",
        "INVALIDATED": "INVALIDATED", "ENDED_FLIP": "ENDED EARLY (flip)", "BREAKOUT": "EARLY BREAKOUT (not confirmed)",
        "RETRACE": "RETRACE WARNING", "LINE_END": "STORY LINE ENDED after the target"}
KIND_NAME = {"A": "A-shape", "V": "V-shape", "OC": "open-close", "flip": "flipped level",
             "align": "protected swing of the W+D+H4 alignment"}
RULE_NAME = {"standard": "key level tap + {ctf} breakout", "sweep_start": "sweep of previous candle + {ctf} breakout",
             "flip": "flip: previous story ended at this level + {ctf} breakout",
             "alignment": "alignment: W break -> D break -> {ctf} break, same way",
             "cadjpy": "CADJPY exception: W trend + D sweep into D open-close level, no {ctf} breakout needed"}
CLOSE_NAME = {"D": "daily", "W": "weekly", "M": "monthly"}


def rule_name(r):
    """Story rule in words, e.g. 'key level tap + H4 breakout, overlap with W level (TP at next key level)'."""
    rule = str(r.get("rule") or "standard")
    base, _, extra = rule.partition("+")
    ctf = STORIES[r["story"]][1]
    s = RULE_NAME.get(base, base).format(ctf=ctf)
    if extra == "overlap":
        s += f", overlap with {HIGHER_TF[r['story']]} level (TP at the next key level)"
    return s


HIGHER_TF = {"D": "W", "W": "M", "M": "-"}
PERIOD = {"D": "day", "W": "week", "M": "month"}


def level_name(r):
    """Origin level type in words, e.g. 'A-shape, D' or 'sweep of previous day high'."""
    k = r.get("level_kind")
    if k == "sweep":
        return f"sweep of previous {PERIOD[r['story']]} {'high' if r['side'] == 'SELL' else 'low'}"
    return f"{KIND_NAME.get(k, k or '-')}, {STORIES[r['story']][0]}"


def kl_name(r):
    """'A-shape KL', 'V-shape KL (flipped)': the shape that drew the line, also for a flipped level (owner request
    2026-10-15: say A / V / OC, not just 'flipped')."""
    k, src = r.get("level_kind"), r.get("level_src")
    if k == "flip":
        return f"{KIND_NAME[src]} KL (flipped)" if src in KIND_NAME else "flipped KL"
    return f"{KIND_NAME.get(k, k or '-')} KL"


def trading_day(t, tf):
    """Which candle a D/W/M candle starting at t (UTC) is, by its 17:00 New York close: 'Thu 8 Oct' (the D candle
    that opens Wed 17:00 New York is Thursday's), 'week of Mon 5 Oct', 'Oct 2026'."""
    k = _key(pd.DatetimeIndex([_ts(t)]), tf)[0]
    if tf == "M":
        return f"{k:%b %Y}"
    day = f"{k:%a} {k.day} {k:%b}"
    return f"week of {day}" if tf == "W" else day


def candle_end(t, tf):
    """Nominal close (UTC) of the tf candle that opens at t."""
    if tf in ("D", "W", "M"):
        return nominal_end(_ts(t), tf)
    return _ts(t) + pd.Timedelta(hours=int(tf[1:]))


def _span(t, tf, tz):
    """'open Wed 7 Oct 23:00 WAT, close Thu 8 Oct 23:00 WAT' for the tf candle that opens at t."""
    return f"open {fmt_time(t, tz)}, close {fmt_time(candle_end(t, tf), tz)}"


def _aligned(r):
    """'Trend aligned with W1/D1' (D story: origin D trend + higher-TF W trend agree with the side), or None."""
    want = "down" if r["side"] == "SELL" else "up"
    otf = STORIES[r["story"]][0]
    tfs = ([TF_LABEL[HIGHER_TF[r["story"]]]] if r.get("htf_trend") == want else []) + \
        ([TF_LABEL[otf]] if r.get("trend") == want else [])
    return f"Trend aligned with {'/'.join(tfs)}" if tfs else None


SHAPE_HELP = {"A": "a top: price closed up into it and turned down; the line is that top close",
              "V": "a bottom: price closed down into it and turned up; the line is that bottom close",
              "OC": "where the move away from a turn started: the close of the first of two same-colour candles"}


def _an(tf):
    return "an" if tf[:1] in "HM" else "a"  # an H4 / an MN1 / a D1 / a W1
ICON = {"TAPPED": "\U0001f440", "BREAKOUT": "⏳", "CONFIRMED": "✅", "RETRACE": "⚠️",
        "CONTINUATION": "➡️", "TARGET_HIT": "\U0001f3af", "INVALIDATED": "❌",
        "ENDED_FLIP": "\U0001f504", "LINE_END": "⛔"}


def format_alert(event, r, tz=DISPLAY_TZ, detail="short"):
    """Telegram BIAS message (never an entry), in sections a person can read (owner 2026-10-16):
    headline (what happened, in words) / KEY LEVEL (shape A / V / OC, price, its candle, flipped?) / STORY SO FAR
    (numbered steps: rejection, external break, confirmation, target, continuation breaks, line end) / CONTEXT
    (higher-TF trend, pullback, Next Day Rule, retrace, rule) / PLAN (target, invalidation, what is next).
    detail (setting alert_detail): short = continuation breaks as a count + the latest; full = every break and each
    candle's open and close. Times in `tz` (setting display_tz)."""
    p = r["pair"]
    fp = lambda x: fmt_price(p, x)  # noqa: E731
    full = detail == "full"
    otf, ctf = STORIES[r["story"]]
    O, C = TF_LABEL[otf], TF_LABEL[ctf]
    sell = r["side"] == "SELL"
    below, above = ("below", "above") if sell else ("above", "below")
    shape = "V" if sell else "A"
    word = "bearish" if sell else "bullish"
    cadjpy = str(r.get("rule") or "").startswith("cadjpy")
    when = lambda t, tf: "\n   \U0001f552 " + (_span(t, tf, tz) if full else  # noqa: E731
                                                 f"{TF_LABEL.get(tf, tf)} candle close "
                                                 f"{fmt_time(candle_end(t, tf), tz)}")
    head = {"TAPPED": f"TAPPED: price is at a key level, waiting for the {C} break",
            "BREAKOUT": f"EARLY {C} BREAK: not confirmed until the {CLOSE_NAME[otf]} close",
            "CONFIRMED": "BIAS CONFIRMED" if cadjpy else "BIAS CONFIRMED (external break)",
            "RETRACE": "RETRACE WARNING (the bias still stands)",
            "CONTINUATION": "CONTINUATION BREAK: the bias continues"
                            + (" after the target" if r.get("status") in AFTER_TARGET else ""),
            "TARGET_HIT": "TARGET HIT",
            "INVALIDATED": "INVALIDATED: the story failed",
            "ENDED_FLIP": "ENDED EARLY: an opposite story took over",
            "LINE_END": "STORY LINE ENDED after the target"}.get(event, HEAD.get(event, event))
    what = {"TAPPED": f"The {O} candle touched the level and closed back {below} it. {_an(C).capitalize()} {C} close {below} point B "
                      f"is needed before there is a story.",
            "BREAKOUT": f"{_an(C).capitalize()} {C} candle closed {below} point B, but the {O} candle is still open.",
            "CONFIRMED": f"The {O} is now {word}: look for {'sells' if sell else 'buys'} only (entries come in "
                         f"their own alert).",
            "RETRACE": f"After the break {_an(C)} {C} candle closed back {above} point B the same {PERIOD[otf]}: lower "
                       f"probability, not invalidated.",
            "CONTINUATION": f"{_an(C).capitalize()} {C} candle closed {below} the next {shape}-shape: the {word} move goes on"
                            + (" (next liquidity)." if r.get("status") in AFTER_TARGET else "."),
            "TARGET_HIT": (f"Price reached the target (external range liquidity): this story is done. Kevin: after "
                           f"the external range, price comes back to the internal range. Wait for that pullback "
                           f"and a NEW story; no trades from this one.") if r.get("_closed_at_target") else
                          f"Price reached the target. The {word} bias still stands until it is proven otherwise.",
            "INVALIDATED": f"The {O} closed back {above} the key level before the target.",
            "ENDED_FLIP": "An opposite key level was rejected and broken: watch for that story's own alert.",
            "LINE_END": f"After the target, the {O} closed back {above} the key level. There is no "
                        f"{STORY_NAME[r['story']].lower()} bias now: wait for the next confirmed story."}.get(event)
    top = [f"{ICON.get(event, '')} {'SELL' if sell else 'BUY'} {p} · {STORY_NAME[r['story']]} story "
           f"· {r.get('chain') or chain(r['story'], r['side'], r.get('htf_trend'))}".strip(), head]
    if what:
        top.append(what)
    if r.get("_bias_note") and event not in ("TARGET_HIT", "LINE_END", "INVALIDATED", "ENDED_FLIP"):
        top.append(r["_bias_note"])  # the outcome headlines already say what happens to the bias
    if r.get("_late"):
        top.append(f"(Confirmed at the {O} close {fmt_time(r['confirm_time'], tz)}; it already ended before this "
                   f"run: see the next message.)")
    out = ["\n".join(top)]

    # KEY LEVEL
    kl = ["\U0001f4cd KEY LEVEL"]
    if r.get("level_kind") == "sweep":
        kl.append(f"{level_name(r).capitalize()} at {fp(r['level'])} ({O})")
    else:
        src = r.get("level_src") if r.get("level_kind") == "flip" else r.get("level_kind")
        kl.append(f"{KIND_NAME.get(src, 'Key level').capitalize()} key level at {fp(r['level'])} ({O})")
        if src in SHAPE_HELP:
            kl.append(f"\u2022 What it is: {SHAPE_HELP[src]}")
        if r.get("level_candle") is not None:
            kl.append(f"• Line from: {O} candle {trading_day(r['level_candle'], otf)} (its close)")
        elif r.get("level_time") is not None:
            kl.append(f"• Formed: {O} candle {trading_day(r['level_time'], otf)}")
        if r.get("level_kind") == "flip":
            kl.append(f"• Flipped: broken"
                      + (f" {trading_day(r['level_time'], otf)}" if r.get("level_time") is not None else "")
                      + f", it now works the other way ({'resistance' if sell else 'support'})")
    out.append("\n".join(kl))

    # STORY SO FAR
    st = ["\U0001f4d6 STORY SO FAR"]
    n = iter(range(1, 20))
    st.append(f"{next(n)}. Rejected: {O} candle {trading_day(r['tap_time'], otf)}, it touched the level and closed "
              f"back {below} it" + (f"\n   \U0001f552 {_span(r['tap_time'], otf, tz)}" if full else ""))
    if cadjpy:
        st.append(f"{next(n)}. No point B: the {O} close back {below} the level confirms it")
    elif event == "BREAKOUT" and r.get("_early"):
        e = r["_early"]
        st.append(f"{next(n)}. {C} closed {below} point B {fp(r['point_b'])} (at {fp(e['close'])})"
                  f"{when(e['time'], ctf)}")
        st.append(f"{next(n)}. Waiting: the {O} candle must also close {below} {fp(r['point_b'])} (Kevin: cancel "
                  f"if it does not)")
    elif r.get("breakout_time") is not None:
        st.append(f"{next(n)}. External break: {C} closed {below} point B {fp(r['point_b'])}"
                  f"{when(r['breakout_time'], ctf)}")
    else:
        st.append(f"{next(n)}. Waiting: a {C} body close {below} point B {fp(r['point_b'])} (no break, no story)")
    if r.get("confirm_time") and event != "BREAKOUT":
        st.append(f"{next(n)}. Confirmed: the {O} candle also closed {below} point B\n   \U0001f552 {O} candle close "
                  f"{fmt_time(r['confirm_time'], tz)}")
    brk = unpack_breaks(r.get("cont_breaks")) if event not in ("TAPPED", "BREAKOUT") else []
    tt = _ts(r["_end_time"]) if r.get("_end_time") else None
    done = event in ("TARGET_HIT", "LINE_END") or r.get("status") == "TARGET_HIT"  # target already reached
    pre = [b for b in brk if tt is None or _ts(b["time"]) < tt]
    post = [b for b in brk if tt is not None and _ts(b["time"]) >= tt]
    new = {(b["level"], b["time"]) for b in r.get("_new_breaks") or []}

    def line(b):
        many = f" (cleared {b['n']} {shape}'s from {fp(b['first'])})" if b.get("n", 1) > 1 else ""
        mark = "NEW " if (b["level"], b["time"]) in new else ""
        return f"   \u2022 {mark}{fp(b['level'])}{many} \u00b7 {C} close {fmt_time(candle_end(b['time'], ctf), tz)}"

    def group(bs, label):
        if not bs:
            return
        st.append(f"{next(n)}. {label}: {len(bs)} {C} close{'s' if len(bs) > 1 else ''} {below} the next "
                  f"{shape}-shape")
        shown = bs if full else ([b for b in bs if (b["level"], b["time"]) in new] or bs[-1:])
        st.extend(line(b) for b in shown)
        if not full and len(bs) > len(shown):
            st.append("   (all of them: setting alert_detail = full, or the Mini App card)")

    group(pre, "Continuation")
    if done and r.get("target") is not None:
        st.append(f"{next(n)}. Target {fp(r['target'])} reached")
    group(post, "After the target")
    if event == "LINE_END" and r.get("line_end"):
        st.append(f"{next(n)}. Line ended: {O} candle {trading_day(r['line_end'], otf)} closed {above} "
                  f"{fp(r['level'])}")
    elif event in ("INVALIDATED", "ENDED_FLIP") and r.get("end_reason"):
        st.append(f"{next(n)}. Ended: {r['end_reason']}")
    out.append("\n".join(st))

    # CONTEXT
    cx = ["\U0001f9ed CONTEXT"]
    h = HIGHER_TF.get(r["story"])
    want = "down" if sell else "up"
    if h in TF_LABEL and r.get("htf_trend") in ("up", "down"):
        cx.append(f"• {TF_LABEL[h]} trend: {'bearish' if r['htf_trend'] == 'down' else 'bullish'} "
                  + ("(agrees)" if r["htf_trend"] == want else "(against this story)"))
    if standing.pullback(r):
        cx.append(f"• {O} structure: {'bullish' if r['trend'] == 'up' else 'bearish'}, so this "
                  f"{'sell' if sell else 'buy'} is a pullback (retracement) inside it, not a bias change")
    elif r.get("trend") == want:
        cx.append(f"• {O} structure: {word} (agrees)")
    nd = _flag(r.get("next_day"))
    if nd is True:
        cx.append(f"• Next Day Rule ✅ the {C} break came after the rejection candle closed")
    elif nd is False:
        cx.append(f"• Next Day Rule ⚠ the {C} broke B before the {O} rejection candle closed (lower "
                  f"probability)")
    if _flag(r.get("retrace")) and not cadjpy and event != "RETRACE":
        cx.append(f"• Retrace ⚠ a later {C} candle closed back {above} point B {fp(r['point_b'])} the "
                  f"same {PERIOD[otf]}")
    cx.append(f"• Rule: {rule_name(r)}")
    out.append("\n".join(cx))

    # PLAN
    pl = ["\U0001f3af PLAN"]
    over = event in ("INVALIDATED", "ENDED_FLIP", "LINE_END")
    if r.get("no_trade") and r.get("no_trade_reason") == ERL_TAKEN:
        first = r.get("_initial_target")
        initial = f"the initial liquidity target {fp(first)}" if first is not None else "the initial liquidity target"
        pl.append(f"• NO_TRADE for entries: {initial} was reached before the {O} confirmation. "
                  "The current entry rule requires a new confirmed story")
    elif r.get("no_trade"):
        pl.append(f"\u2022 NO_TRADE: {r.get('no_trade_reason') or 'filter'}")
    elif event == "TAPPED":
        pl.append(f"• NO_TRADE: wait for a {C} body close {below} point B, then the {O} confirmation close {below} point B")
    elif event == "BREAKOUT":
        pl.append(f"• NO_TRADE: the {C} break has happened; wait for the {O} confirmation close {below} point B")
    if not over:
        if not done:
            replaced = (r.get("no_trade_reason") == ERL_TAKEN and r.get("_initial_target") is not None
                        and r.get("target") is not None and r["_initial_target"] != r["target"])
            label = "Replacement bias target" if replaced else "Target"
            pl.append(f"• {label}: {fp(r['target'])}" if r.get("target") is not None else
                      "• Target: set when the story confirms")
        pl.append(f"• Invalid if the {O} closes {above} {fp(r['invalidation'])}")
        if r.get("_closed_at_target"):
            pass
        elif done or r.get("status") in AFTER_TARGET:
            pl.append(f"\u2022 Next: {_an(C)} {C} close {below} the next {shape}-shape continues the line; "
                      f"{_an(O)} {O} close {above} {fp(r['level'])} ends it")
    else:
        pl.append("\u2022 Nothing to do on this story now: wait for the next confirmed story")
    if r.get("_closed_at_target") and event == "TARGET_HIT":
        pl[1:] = [f"\u2022 Story closed: no continuation alerts or entries from it",
                  f"\u2022 Next: a pullback into the internal range, then a new rejection + {C} break = a new "
                  f"story (its own alert)"]
    out.append("\n".join(pl))
    out.append(f"\U0001f552 Times {_ts(r['tap_time']).tz_convert(tz).tzname()} \u00b7 Bias only. Not an entry "
               f"signal: wait for an entry alert")
    return "\n\n".join(out)


def summary_line(pair, rows, close_at_target=False):
    """'EURUSD: W BUY tapped (...), D SELL B 1.08120 T 1.07600' + the standing bias of story TFs whose story is
    over (target reached etc.), e.g. 'D BEARISH bias (target reached, bias continues)' (slk.standing)."""
    act = sorted((r for r in rows if r["status"] in ACTIVE), key=lambda r: "MWD".index(r["story"]))
    stand = {s: standing.standing(rows, s, close_at_target=close_at_target) for s in "MWD"
             if any(r["story"] == s for r in rows)}
    parts = []
    for r in act:
        s = f"{r['story']} {r['side']}"
        rule = str(r.get("rule") or "standard")
        if rule not in ("standard", "sweep_start"):
            s += f" [{rule}]"
        if r["status"] == "TAPPED":
            s += " tapped (NO_TRADE until breakout)"
        else:
            s += f" B {fmt_price(pair, r['point_b'])} T {fmt_price(pair, r['target'])}"
        parts.append(s)
    for st, b in stand.items():
        if b["side"] and b["state"] != "story active":
            parts.append(f"{st} {standing.WORD[b['side']]} bias ({b['state']})")
    if not parts:
        return f"{pair}: NO_TRADE (no story)"
    line = f"{pair}: " + ", ".join(parts)
    m, w = (stand.get(x, {}).get("side") for x in ("M", "W"))
    if m and w and m != w:
        line += " -> NO_TRADE (M/W disagree)"
    return line


def format_summary(now, by_pair, kill_switch="off", close_at_target=False):
    ny = _ts(now).tz_convert("America/New_York")
    head = [f"SLK daily BIAS {ny:%a %Y-%m-%d} (NY close) - direction only, not entries",
            "Trading: OFF (kill switch)" if str(kill_switch).lower() == "on" else "Trading: kill switch off"]
    return "\n".join(head + [summary_line(p, rows, close_at_target) for p, rows in by_pair.items()])


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
             "INVALIDATED": "alert_ended", "ENDED_FLIP": "alert_ended", "RETRACE": "alert_confirmed",
             "BREAKOUT": "early_breakout_alert", "CONTINUATION": "alert_continuation", "LINE_END": "alert_ended"}


def build_cfg(stored=None, overrides=None):
    """(story cfg, entry cfg, typed settings) from stored strings (slk/settings.py schema); anything missing
    or invalid falls back to the code defaults (Kevin's rules). `overrides` (--cfg JSON) win over both."""
    vals = S.load(stored)
    cfg = {**DEFAULT, **S.story_cfg(vals), "use_monthly": "M" in vals["stories"],
           "erl_taken_no_trade": vals["erl_taken_no_trade"], "close_at_target": vals["close_at_target"],
           **(overrides or {})}
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
        trends = {st: tf_trend(drop_forming(drop_forming(h1, "H1", now), STORIES[st][0], now), st, cfg)
                  for st in stories}
        _save_memo(pair, memo)
        ents = entry_rows(pair, drop_forming(h1, "H1", now), rows, {}, cfg, ecfg=ecfg, keep_key=True) \
            if entries_on else []
        return {"pair": pair, "rows": rows, "entries": ents, "trends": trends}
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
                    print(format_alert(row["status"], row, vals["display_tz"]) + "\n")
                    if row.get("_early"):
                        print(format_alert("BREAKOUT", row, vals["display_tz"]) + "\n")
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
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"run_id={run_id}\n")
    print(f"run {run_id}: planned {planned:%H:%M} started {started:%H:%M:%S} UTC "
          f"(late {int((started - planned).total_seconds() // 60)} min)", flush=True)

    errors, sent, by_pair, pairs, note = [], 0, {}, [], ""
    early_sent, early_dirty = {}, False
    try:
        cfg, ecfg, vals = build_cfg(_load_settings(db), overrides)  # re-read every run
        tz = vals["display_tz"]
        try:
            early_sent = json.loads(db.get_setting("early_alerts_sent") or "{}")
        except (ValueError, TypeError):
            early_sent = {}
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
                bias_notes(alerts, old, writes, res.get("trends"), cfg.get("close_at_target", False))
                for st, t in (res.get("trends") or {}).items():
                    if st in stories:
                        db.upsert_tf_state(p, st, t)
                for ev, r in alerts_enabled(filter_alerts(alerts), vals):
                    sent += send_telegram(format_alert(ev, r, tz, vals["alert_detail"]))
                if vals["early_breakout_alert"]:
                    early, early_sent = early_alerts(new, early_sent, now)
                    for ev, r in early:
                        sent += send_telegram(format_alert(ev, r, tz, vals["alert_detail"]))
                        early_dirty = True
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
                stored = db.get_entries(p)  # after the writes above
                bstat = {r.get("id"): r["status"] for r in by_pair[p]}
                for e, f in cancel_entries(stored, bstat):
                    db.update_entry_result(e["id"], e["status"], f)
                closed = drop_forming(h1, "H1", now)  # closed H1 bars only (no look-ahead)
                for e, f, evs in track_entries(stored, closed, ecfg):
                    if db.update_entry_result(e["id"], e["status"], f) and vals["alert_entry"]:  # write first, then
                        for ev in evs:                                                           # alert once
                            sent += send_telegram(format_result_alert(ev, e, f))
                print(f"{p}: {len(new)} stories, {len(writes)} written, {len(alerts)} alerts, "
                      f"{len(ew)} entries written", flush=True)
            except Exception as e:  # one bad pair must not stop the others
                errors.append(f"{p}: {type(e).__name__}: {e}")
                traceback.print_exc()
        print(f"timing: download {t_cpu - t_dl:.1f}s, engine {t_db - t_cpu:.1f}s, db+alerts "
              f"{time.monotonic() - t_db:.1f}s", flush=True)
        if by_pair and vals["daily_summary"] and summary_due(started, db.get_setting("last_summary")):
            if send_telegram(format_summary(started, by_pair, kill, cfg.get("close_at_target", False))) or not os.environ.get("TELEGRAM_BOT_TOKEN"):
                db.set_setting("last_summary", _ts(started).tz_convert("America/New_York").strftime("%Y-%m-%d"))
        if early_dirty:
            db.set_setting("early_alerts_sent", json.dumps(early_sent, sort_keys=True))
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
