"""The story line (bias): tap-reject-close on the origin TF, breakout of point B one TF lower. STRATEGY §2."""
import numpy as np
import pandas as pd

from .candles import resample
from .levels import find_levels, run_levels
from .structure import SwingBook, pivots, swings, trend

STORIES = {"M": ("M", "W"), "W": ("W", "D"), "D": ("D", "H4")}
HIGHER = {"D": "W", "W": "M", "M": None}

DEFAULT = {
    "level_pivot": 1,       # A/V must be a close-line turning point of this order
    "swing_pivot": 2,       # swings for trend / point B / targets
    "use_oc": True,
    "trend_filter": True,   # only levels that agree with the origin-TF trend
    "tap_tol_pips": 1.0,    # wick within this distance of the line counts as a touch
    "max_wait": 5,          # origin bars from tap to breakout
    "max_retaps": 3,        # more re-taps before breakout = messy, skip
    "same_bar_close": True, # origin bar holding the breakout must close beyond B too
    "htf_filter": True,     # never against the higher-TF trend (STRATEGY §2 no-trade rules)
    "stop_buffer_pips": 2.0,
    "max_hold": 20,         # origin bars after confirmation
    "mw_conflict_filter": True,  # latest M and W stories point opposite ways -> D stories are NO_TRADE (§2)
}
# Point B is broken only by an EXTERNAL break: a confirm-TF body close beyond B, the last opposite swing before
# the first tap (+ same_bar_close). Kevin's two confirmations, "sweep and break" (advanced structure: sweep of
# liquidity, then BOS) or a plain "breakout" [T story-line-pt2@297-441, 571-647], both end in that same close
# beyond the last V/A before the tap [F frames_D story-line-pt2 sheet_001-021 + Corrections: "BMS" (sweep+break)
# and "BO" are both a body close through the last A/V before the tap]; the sweep only
# labels which one it was (story["break_kind"]). Internal breaks (BOS after the tap) never confirm the bias;
# they are for continuation entries only (slk/entry.py). Deliberately no setting changes this.


def _side_at(stories, t):
    """Side of the latest story confirmed at or before t (None if none)."""
    best = None
    for s in stories:
        c = s.get("confirm_time")
        if c is None or (t is not None and pd.Timestamp(c) > pd.Timestamp(t)):
            continue
        if best is None or pd.Timestamp(c) > pd.Timestamp(best["confirm_time"]):
            best = s
    return None if best is None else best["side"]


def mw_conflict(m_stories, w_stories, t=None):
    """True when the latest M and W stories (confirmed at or before t) point opposite ways. STRATEGY §2."""
    m, w = _side_at(m_stories, t), _side_at(w_stories, t)
    return m is not None and w is not None and m != w


def apply_mw_filter(d_stories, m_stories, w_stories, cfg=None):
    """D stories with `no_trade` set when M and W disagreed at the D story's confirmation. With
    cfg['mw_conflict_filter'] off, all D stories pass unchanged. Use in the backtest before scoring."""
    cfg = {**DEFAULT, **(cfg or {})}
    if not cfg["mw_conflict_filter"]:
        return list(d_stories)
    return [{**d, "no_trade": mw_conflict(m_stories, w_stories, d.get("confirm_time") or d.get("tap_time"))}
            for d in d_stories]


def pip(pair):
    return 0.01 if pair.endswith("JPY") else 0.0001


def find_stories(pair, h1, story, cfg=None):
    cfg = {**DEFAULT, **(cfg or {})}
    otf, ctf = STORIES[story]
    ob, cb = resample(h1, otf), resample(h1, ctf)
    P = pip(pair)
    tol = cfg["tap_tol_pips"] * P
    levels = run_levels(ob, find_levels(ob, cfg), tol)
    opiv, cpiv = pivots(ob["close"], cfg["swing_pivot"]), pivots(cb["close"], cfg["swing_pivot"])
    htf = HIGHER[story]
    hb = resample(h1, htf) if htf else None
    hpiv = pivots(hb["close"], cfg["swing_pivot"]) if htf else None

    O = {k: ob[k].to_numpy() for k in ("open", "high", "low", "close")}
    C = {k: cb[k].to_numpy() for k in ("open", "high", "low", "close")}
    o_start, o_end = ob["start"].to_numpy(), ob["end"].to_numpy()
    c_start, c_end = cb["start"].to_numpy(), cb["end"].to_numpy()
    c2o = np.searchsorted(o_start, c_start, side="right") - 1  # origin bar holding each confirm bar
    X = _Ctx(O, c2o, opiv, cpiv, hb, hpiv, levels)

    taps = {}
    for lv in levels:
        for b, kind, _ in lv.events:
            if kind == "tap":
                taps.setdefault(b, []).append(lv)

    rows, busy_until = [], -1
    for bar in sorted(taps):
        if bar <= busy_until or bar < 2:
            continue
        tr = trend(X.osw.at(bar - 1), O["close"][bar - 1])
        if cfg["trend_filter"]:
            if tr == "range":
                continue
            cands = [lv for lv in taps[bar] if lv.side == ("sell" if tr == "down" else "buy")]
        else:
            cands = taps[bar]
        if not cands:
            continue
        lv = max(cands, key=lambda x: x.born)  # most recent fresh level
        h_tr = X.htf_trend(o_start[bar]) if htf else None
        if cfg["htf_filter"] and _against(lv.side, h_tr):
            continue
        r = _confirm(lv, bar, cfg, P, O, C, o_start, o_end, c_start, c_end, c2o, X)
        if r is None:
            continue
        r.update(pair=pair, story=story, trend=tr, level_kind=lv.kind, level=lv.price,
                 tap_time=str(o_start[bar])[:16])
        if htf:
            r["htf_trend"] = h_tr
        rows.append(r)
        busy_until = r.pop("_busy")
    return rows


def _htf_trend(hb, hpiv, t):
    """Trend of the higher TF on its last bar closed before time t."""
    hi = np.searchsorted(hb["start"].to_numpy(), t, side="right") - 2  # last closed HTF bar
    return trend(swings(hpiv, hi), hb["close"].iat[hi]) if hi >= 2 else "range"


class _Ctx:
    """Per-call caches (speed only, same results): swing lists by `upto`, HTF arrays, first event bar of each
    level, first/last confirm bar of each origin bar."""

    def __init__(self, O, c2o, opiv, cpiv, hb, hpiv, levels):
        self.osw, self.csw = SwingBook(opiv), SwingBook(cpiv)
        if hb is not None:
            self.h_start, self.h_close, self.hsw = hb["start"].to_numpy(), hb["close"].to_numpy(), SwingBook(hpiv)
        n = len(O["close"])
        self.first_k = np.searchsorted(c2o, np.arange(n + 1), "left")  # first confirm bar of origin bar i
        self.levels = levels
        self.lv_buy = np.array([lv.side == "buy" for lv in levels], dtype=bool)
        self.lv_born = np.array([lv.born for lv in levels], dtype=np.int64)
        self.lv_first = np.array([lv.events[0][0] if lv.events else np.iinfo(np.int64).max for lv in levels],
                                 dtype=np.int64)

    def htf_trend(self, t):
        """= _htf_trend(hb, hpiv, t)."""
        hi = np.searchsorted(self.h_start, t, side="right") - 2
        return trend(self.hsw.at(hi), self.h_close[hi]) if hi >= 2 else "range"

    def fresh_prices(self, buy, upto):
        """Prices of levels of this side born by bar `upto` with no event (tap/break) up to that bar, in order."""
        m = (self.lv_buy == buy) & (self.lv_born <= upto) & (self.lv_first > upto)
        return [self.levels[i].price for i in np.flatnonzero(m)]


def _against(side, htf_trend):
    return (side == "sell" and htf_trend == "up") or (side == "buy" and htf_trend == "down")


def _confirm(lv, bar, cfg, P, O, C, o_start, o_end, c_start, c_end, c2o, X):
    sell = lv.side == "sell"
    tol = cfg["tap_tol_pips"] * P
    # first confirm-TF bar inside the tap bar that touched the level = "price first tapped"
    ks = np.arange(X.first_k[bar], X.first_k[bar + 1])
    if not len(ks):
        return None
    touch = [k for k in ks if (C["high"][k] >= lv.price - tol if sell else C["low"][k] <= lv.price + tol)]
    k0 = touch[0] if touch else ks[0]
    sw = X.csw.at(k0 - 1)
    pts = [s[2] for s in sw if s[1] == ("L" if sell else "H")]
    if not pts:
        return None
    B = pts[-1]
    if (sell and B >= lv.price) or (not sell and B <= lv.price):
        return None

    last_o = min(bar + cfg["max_wait"], len(O["close"]) - 1)
    retaps, k, brk = 0, k0, None
    while k < len(C["close"]) and c2o[k] <= last_o:
        oi = c2o[k]
        if oi > bar and k == X.first_k[oi]:  # new origin bar starts: judge the previous one
            prev = oi - 1
            if prev > bar:
                if (O["close"][prev] > lv.price) if sell else (O["close"][prev] < lv.price):
                    return None  # body close through the origin level before breakout: invalid
                if (O["high"][prev] >= lv.price - tol) if sell else (O["low"][prev] <= lv.price + tol):
                    retaps += 1
                    if retaps > cfg["max_retaps"]:
                        return None  # messy level
        if (C["close"][k] < B) if sell else (C["close"][k] > B):
            ok = (O["close"][oi] < B) if sell else (O["close"][oi] > B)
            if not cfg["same_bar_close"] or ok:
                brk = k
                break
            k = X.first_k[oi + 1]  # cancelled for this day; try from the next one
            continue
        k += 1
    if brk is None:
        return None
    kind = _break_kind(sell, sw, k0, brk, C)

    # confirmed when the breakout bar and the tap bar have closed, and (same_bar_close) the origin bar holding
    # the breakout too: its close beyond B was used above, so it must not be known earlier (no look-ahead)
    need_end = o_end[c2o[brk]] if cfg["same_bar_close"] else o_end[bar]
    conf_k = brk
    while conf_k + 1 < len(c_end) and c_end[conf_k] < need_end:
        conf_k += 1
    ref = C["close"][conf_k]
    conf_o = c2o[conf_k]
    closed_o = int(np.searchsorted(o_end, c_end[conf_k], "right")) - 1  # last origin bar closed at confirmation

    # target: nearest opposite fresh level or origin-TF swing beyond the entry reference
    cands = X.fresh_prices(sell, closed_o)  # opposite side: buy levels for a sell
    cands += [s[2] for s in X.osw.at(closed_o) if s[1] == ("L" if sell else "H")]
    cands = [x for x in cands if (x < ref if sell else x > ref)]
    if not cands:
        return None
    target = max(cands) if sell else min(cands)
    stop = (O["high"][bar] + cfg["stop_buffer_pips"] * P) if sell else (O["low"][bar] - cfg["stop_buffer_pips"] * P)
    risk = (stop - ref) if sell else (ref - stop)
    if risk <= 0:
        return None
    R = abs(target - ref) / risk

    # outcome A (trade): target vs stop on confirm-TF bars. Outcome B (Kevin): target vs origin close through level
    end_o = min(conf_o + cfg["max_hold"], len(O["close"]) - 1)
    out, res, inv, exit_k = "timeout", None, "open", None
    k = conf_k + 1
    while k < len(C["close"]) and c2o[k] <= end_o:
        hit_stop = C["high"][k] >= stop if sell else C["low"][k] <= stop
        hit_tgt = C["low"][k] <= target if sell else C["high"][k] >= target
        if out == "timeout":
            if hit_stop:
                out, res, exit_k = "loss", -1.0, k
            elif hit_tgt:
                out, res, exit_k = "win", R, k
        if inv == "open":
            if hit_tgt:
                inv = "target"
            elif k == X.first_k[c2o[k] + 1] - 1 and ((O["close"][c2o[k]] > lv.price) if sell else (O["close"][c2o[k]] < lv.price)):
                inv = "invalidated"
        if out != "timeout" and inv != "open":
            break
        k += 1
    last = min(k, len(C["close"])) - 1  # last bar inside the hold window (k is the first one past it)
    if out == "timeout":
        res = ((ref - C["close"][last]) if sell else (C["close"][last] - ref)) / risk
    done_o = c2o[exit_k] if exit_k is not None else c2o[last]
    return {
        "side": "SELL" if sell else "BUY", "B": B, "breakout_time": str(c_start[brk])[:16],
        "confirm_time": str(c_end[conf_k])[:16], "entry_ref": ref, "target": target, "stop": stop,
        "R": round(R, 2), "outcome": out, "result_R": round(res, 2), "kevin_outcome": inv,
        "stop_pips": round(risk / P, 1), "break_kind": kind, "_busy": int(done_o),
    }


def _break_kind(sell, sw, k0, brk, C):
    """Label only (the break itself is always the external close beyond B). "sweep_break" when, between the
    first tap and the breakout, a confirm-TF wick went beyond the last swing high (sell; low for buy) made
    before the tap and the candle closed back inside: a sweep of that liquidity, then the break (advanced
    structure = sweep -> BOS) [T story-line-pt2@405-436; notes_structure §4]. Otherwise "breakout"."""
    liq = [s[0] for s in sw if s[1] == ("H" if sell else "L")]
    if not liq:
        return "breakout"
    x = C["high"][liq[-1]] if sell else C["low"][liq[-1]]
    for k in range(k0, brk):
        if (C["high"][k] > x and C["close"][k] < x) if sell else (C["low"][k] < x and C["close"][k] > x):
            return "sweep_break"
    return "breakout"


def current_tap(pair, h1, story, cfg=None):
    """Live 'current state': the latest tap-reject-close on a fresh, trend-agreeing level that has NOT broken
    out yet and is still within max_wait origin bars (STRATEGY §2 step 3, no-trade rule 1). Same rules as
    find_stories/_confirm. `h1` must end with closed bars only. Returns a dict (status 'TAPPED') or None.
    A tap that already broke out is find_stories' job, so None is returned for it."""
    cfg = {**DEFAULT, **(cfg or {})}
    otf, ctf = STORIES[story]
    ob, cb = resample(h1, otf), resample(h1, ctf)
    P = pip(pair)
    tol = cfg["tap_tol_pips"] * P
    levels = run_levels(ob, find_levels(ob, cfg), tol)
    opiv, cpiv = pivots(ob["close"], cfg["swing_pivot"]), pivots(cb["close"], cfg["swing_pivot"])
    O = {k: ob[k].to_numpy() for k in ("open", "high", "low", "close")}
    C = {k: cb[k].to_numpy() for k in ("open", "high", "low", "close")}
    o_start = ob["start"].to_numpy()
    c2o = np.searchsorted(o_start, cb["start"].to_numpy(), side="right") - 1
    last = len(O["close"]) - 1
    htf = HIGHER[story]
    hb = resample(h1, htf) if htf else None
    hpiv = pivots(hb["close"], cfg["swing_pivot"]) if htf else None
    X = _Ctx(O, c2o, opiv, cpiv, hb, hpiv, levels)

    taps = {}
    for lv in levels:
        for b, kind, _ in lv.events:
            if kind == "tap":
                taps.setdefault(b, []).append(lv)

    for bar in sorted(taps, reverse=True):
        if bar < last - cfg["max_wait"]:
            break
        if bar < 2:
            continue
        tr = trend(X.osw.at(bar - 1), O["close"][bar - 1])
        if cfg["trend_filter"]:
            if tr == "range":
                continue
            cands = [lv for lv in taps[bar] if lv.side == ("sell" if tr == "down" else "buy")]
        else:
            cands = taps[bar]
        if not cands:
            continue
        lv = max(cands, key=lambda x: x.born)
        if htf and cfg["htf_filter"] and _against(lv.side, X.htf_trend(o_start[bar])):
            continue
        sell = lv.side == "sell"
        ks = np.arange(X.first_k[bar], X.first_k[bar + 1])
        if not len(ks):
            continue
        touch = [k for k in ks if (C["high"][k] >= lv.price - tol if sell else C["low"][k] <= lv.price + tol)]
        k0 = touch[0] if touch else ks[0]
        pts = [s[2] for s in X.csw.at(k0 - 1) if s[1] == ("L" if sell else "H")]
        if not pts:
            continue
        B = pts[-1]
        if (sell and B >= lv.price) or (not sell and B <= lv.price):
            continue

        state, retaps = "TAPPED", 0
        for oi in range(bar, last + 1):
            for k in range(max(k0, X.first_k[oi]), X.first_k[oi + 1]):
                if (C["close"][k] < B) if sell else (C["close"][k] > B):
                    ok = (O["close"][oi] < B) if sell else (O["close"][oi] > B)
                    if not cfg["same_bar_close"] or ok:
                        return None  # broke out: a confirmed story (or rejected by find_stories)
            if oi > bar:
                if (O["close"][oi] > lv.price) if sell else (O["close"][oi] < lv.price):
                    state = "INVALIDATED"
                    break
                if (O["high"][oi] >= lv.price - tol) if sell else (O["low"][oi] <= lv.price + tol):
                    retaps += 1
                    if retaps > cfg["max_retaps"]:
                        state = "MESSY"
                        break
        if state != "TAPPED":
            continue

        ref = O["close"][last]
        tg = X.fresh_prices(sell, last)
        tg += [s[2] for s in X.osw.at(last) if s[1] == ("L" if sell else "H")]
        tg = [x for x in tg if (x < min(ref, B) if sell else x > max(ref, B))]
        return {
            "pair": pair, "story": story, "side": "SELL" if sell else "BUY", "status": "TAPPED", "trend": tr,
            "level_kind": lv.kind, "level": lv.price, "B": B,
            "target": (max(tg) if sell else min(tg)) if tg else None,
            "tap_time": str(o_start[bar])[:16], "bars_left": int(bar + cfg["max_wait"] - last),
        }
    return None
