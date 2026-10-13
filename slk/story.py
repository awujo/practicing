"""The story line (bias): tap-reject-close on the origin TF, breakout of point B one TF lower. STRATEGY §2."""
import numpy as np

from .candles import resample
from .levels import find_levels, run_levels
from .structure import pivots, swings, trend

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
}


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

    taps = {}
    for lv in levels:
        for b, kind, _ in lv.events:
            if kind == "tap":
                taps.setdefault(b, []).append(lv)

    rows, busy_until = [], -1
    for bar in sorted(taps):
        if bar <= busy_until or bar < 2:
            continue
        tr = trend(swings(opiv, bar - 1), O["close"][bar - 1])
        if cfg["trend_filter"]:
            if tr == "range":
                continue
            cands = [lv for lv in taps[bar] if lv.side == ("sell" if tr == "down" else "buy")]
        else:
            cands = taps[bar]
        if not cands:
            continue
        lv = max(cands, key=lambda x: x.born)  # most recent fresh level
        h_tr = _htf_trend(hb, hpiv, o_start[bar]) if htf else None
        if cfg["htf_filter"] and _against(lv.side, h_tr):
            continue
        r = _confirm(lv, bar, cfg, P, O, C, o_start, o_end, c_start, c_end, c2o, cpiv, opiv, levels)
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


def _against(side, htf_trend):
    return (side == "sell" and htf_trend == "up") or (side == "buy" and htf_trend == "down")


def _confirm(lv, bar, cfg, P, O, C, o_start, o_end, c_start, c_end, c2o, cpiv, opiv, levels):
    sell = lv.side == "sell"
    tol = cfg["tap_tol_pips"] * P
    # first confirm-TF bar inside the tap bar that touched the level = "price first tapped"
    ks = np.arange(np.searchsorted(c2o, bar, "left"), np.searchsorted(c2o, bar, "right"))
    if not len(ks):
        return None
    touch = [k for k in ks if (C["high"][k] >= lv.price - tol if sell else C["low"][k] <= lv.price + tol)]
    k0 = touch[0] if touch else ks[0]
    sw = swings(cpiv, k0 - 1)
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
        if oi > bar and k == np.searchsorted(c2o, oi, "left"):  # new origin bar starts: judge the previous one
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
            k = np.searchsorted(c2o, oi, "right")  # cancelled for this day; try from the next one
            continue
        k += 1
    if brk is None:
        return None

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
    cands = []
    for o in levels:
        if o.side == ("buy" if sell else "sell") and o.born <= closed_o and not any(e[0] <= closed_o for e in o.events):
            cands.append(o.price)
    cands += [s[2] for s in swings(opiv, closed_o) if s[1] == ("L" if sell else "H")]
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
            elif k == np.searchsorted(c2o, c2o[k], "right") - 1 and ((O["close"][c2o[k]] > lv.price) if sell else (O["close"][c2o[k]] < lv.price)):
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
        "stop_pips": round(risk / P, 1), "_busy": int(done_o),
    }


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
        tr = trend(swings(opiv, bar - 1), O["close"][bar - 1])
        if cfg["trend_filter"]:
            if tr == "range":
                continue
            cands = [lv for lv in taps[bar] if lv.side == ("sell" if tr == "down" else "buy")]
        else:
            cands = taps[bar]
        if not cands:
            continue
        lv = max(cands, key=lambda x: x.born)
        if htf and cfg["htf_filter"] and _against(lv.side, _htf_trend(hb, hpiv, o_start[bar])):
            continue
        sell = lv.side == "sell"
        ks = np.arange(np.searchsorted(c2o, bar, "left"), np.searchsorted(c2o, bar, "right"))
        if not len(ks):
            continue
        touch = [k for k in ks if (C["high"][k] >= lv.price - tol if sell else C["low"][k] <= lv.price + tol)]
        k0 = touch[0] if touch else ks[0]
        pts = [s[2] for s in swings(cpiv, k0 - 1) if s[1] == ("L" if sell else "H")]
        if not pts:
            continue
        B = pts[-1]
        if (sell and B >= lv.price) or (not sell and B <= lv.price):
            continue

        state, retaps = "TAPPED", 0
        for oi in range(bar, last + 1):
            for k in range(max(k0, np.searchsorted(c2o, oi, "left")), np.searchsorted(c2o, oi, "right")):
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
        tg = [o.price for o in levels if o.side == ("buy" if sell else "sell") and o.born <= last
              and not any(e[0] <= last for e in o.events)]
        tg += [s[2] for s in swings(opiv, last) if s[1] == ("L" if sell else "H")]
        tg = [x for x in tg if (x < min(ref, B) if sell else x > max(ref, B))]
        return {
            "pair": pair, "story": story, "side": "SELL" if sell else "BUY", "status": "TAPPED", "trend": tr,
            "level_kind": lv.kind, "level": lv.price, "B": B,
            "target": (max(tg) if sell else min(tg)) if tg else None,
            "tap_time": str(o_start[bar])[:16], "bars_left": int(bar + cfg["max_wait"] - last),
        }
    return None
