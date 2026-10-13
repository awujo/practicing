"""Entry model (stage 2): the 4-candle continuation after a CONFIRMED story. STRATEGY §3.

Sell (a buy is the mirror image), on the entry timeframe, after the story's external breakout:
  c1 bull + c2 bear  -> A-shape; thin line at the shared body price (c1 close)
  c3                 -> wick pokes up to the line (within tolerance) and the body closes back below it
  c4                 -> impulsive bear candle closing below the lows of c1..c3 (internal BOS)
  entry              -> sell limit at the line (retest); stop above c3 high + buffer
  TP1                -> nearest unbroken entry-TF swing low between tp1_min_rr and tp1_max_rr R (else tp1_min_rr R)
  TP2                -> the story target

The most recent qualifying pattern replaces an older pending one. A pending level that is not
retested within `retest_bars` entry-TF bars is MISSED (no chasing). Entries are taken on the first
entry TF of the ladder that has any qualifying pattern (D story: H4 -> H2 -> H1).

Public:
  find_entries(pair, h1, stories, cfg)    -> one entry dict per story (status TRIGGERED/PENDING/MISSED/NO_SETUP/SKIPPED)
  simulate(entry, h1_bars, cfg)           -> TP1 / TP2 results in R on H1 bars (backtest)
"""
import numpy as np
import pandas as pd

from .candles import resample
from .story import DEFAULT as STORY_DEFAULT, STORIES, pip
from .structure import pivots

ENTRY_TFS = {"D": ("H4", "H2", "H1"), "W": ("D", "H4"), "M": ("W", "D")}

DEFAULT = {
    "tap_tol_pips": 1.0,       # c3 wick within this distance of the line counts as a touch (same as story)
    "impulse_mult": 1.0,       # c4 body >= this x average body of the previous `impulse_lookback` bars
    "impulse_lookback": 10,
    "stop_buffer_pips": 1.0,   # stop = c3 extreme + buffer
    "max_stop_pips": 20.0,     # wider stop = pattern does not qualify (JPY pairs: same number of pips)
    "avoid_pairs": ["AUDNZD", "NZDCHF"],  # wide spread
    "retest_bars": 12,         # entry-TF bars after c4 to wait for the retest, then MISSED
    "skip_first": True,        # no pattern formed at or before the top of the first retracement after the breakout
    "pivot": 2,                # close-line pivot order used for the first retracement and TP1 swing levels
    "tp1_min_rr": 1.5,
    "tp1_max_rr": 3.0,         # a swing level further than this is not TP1; TP1 falls back to tp1_min_rr R
    "min_rr_tp2": 1.0,         # story target must give at least this R from the entry
    "max_story_bars": None,    # origin bars after confirmation to look for entries (None = story max_hold)
    "max_trade_bars": 60,      # entry-TF bars a trade is held before it is closed at market
}

TF_HOURS = {"H1": 1, "H2": 2, "H4": 4, "D": 24, "W": 120, "M": 520}


def _t(s):
    return np.datetime64(str(s)[:16].replace(" ", "T"), "ns")


def _s(t):
    return str(pd.Timestamp(t))[:16]


def _arrays(bars):
    d = {k: bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close")}
    for k in ("start", "end"):  # naive UTC datetime64 for fast searchsorted
        t = pd.to_datetime(bars[k])
        d[k] = (t.dt.tz_convert(None) if t.dt.tz is not None else t).to_numpy(dtype="datetime64[ns]")
    return d


def patterns(B, sell, cfg, P):
    """All 4-candle continuation patterns on bar arrays B. Returns list of dicts (c1 index, line, c3 extreme)."""
    o, h, l, c = B["open"], B["high"], B["low"], B["close"]
    n = len(c)
    if n < 5:
        return []
    tol = cfg["tap_tol_pips"] * P
    body = np.abs(c - o)
    lb = cfg["impulse_lookback"]
    avg = pd.Series(body).rolling(lb, min_periods=3).mean().shift(1).to_numpy()  # avg before each bar
    i = np.arange(n - 3)
    i1, i2, i3 = i + 1, i + 2, i + 3
    if sell:
        lvl = c[i]
        ok = (c[i] > o[i]) & (c[i1] < o[i1])                                  # A-shape
        ok &= (h[i2] >= lvl - tol) & (c[i2] < lvl) & (h[i2] > np.maximum(o[i2], c[i2]))  # c3 wick rejection
        inner = np.minimum(np.minimum(l[i], l[i1]), l[i2])
        ok &= (c[i3] < o[i3]) & (c[i3] < inner)                               # c4 bear body close beyond
    else:
        lvl = c[i]
        ok = (c[i] < o[i]) & (c[i1] > o[i1])                                  # V-shape
        ok &= (l[i2] <= lvl + tol) & (c[i2] > lvl) & (l[i2] < np.minimum(o[i2], c[i2]))
        inner = np.maximum(np.maximum(h[i], h[i1]), h[i2])
        ok &= (c[i3] > o[i3]) & (c[i3] > inner)
    ok &= np.nan_to_num(body[i3] >= cfg["impulse_mult"] * avg[i3], nan=False).astype(bool)
    return [{"c1": int(k), "line": float(lvl[k]), "c3x": float(h[k + 2] if sell else l[k + 2])}
            for k in np.flatnonzero(ok)]


class _Pair:
    """Per-pair cache of resampled bars, pivots and patterns."""

    def __init__(self, pair, h1, cfg):
        self.pair, self.cfg, self.P = pair, cfg, pip(pair)
        self.h1 = _arrays(resample(h1, "H1"))
        self._bars, self._piv, self._pat = {}, {}, {}
        self.h1df = h1

    def bars(self, tf):
        if tf not in self._bars:
            self._bars[tf] = _arrays(resample(self.h1df, tf))
        return self._bars[tf]

    def piv(self, tf):
        if tf not in self._piv:
            self._piv[tf] = pivots(self.bars(tf)["close"], self.cfg["pivot"])
        return self._piv[tf]

    def pats(self, tf, sell):
        if (tf, sell) not in self._pat:
            self._pat[(tf, sell)] = patterns(self.bars(tf), sell, self.cfg, self.P)
        return self._pat[(tf, sell)]


def _story_end(px, story, sell, t_conf, scfg, cfg):
    """Time after which no new entry is taken: target touched, origin close back through the level, or max bars."""
    otf = STORIES[story["story"]][0]
    O = px.bars(otf)
    k0 = int(np.searchsorted(O["end"], t_conf, "right"))  # first origin bar still open at confirmation
    if k0 >= len(O["close"]):
        return px.h1["end"][-1]
    nmax = cfg["max_story_bars"] or scfg["max_hold"]
    end = O["end"][min(k0 + nmax, len(O["close"]) - 1)]
    lvl = story["level"]
    seg = O["close"][k0:k0 + nmax + 1]
    bad = np.flatnonzero(seg > lvl if sell else seg < lvl)
    if len(bad):
        end = min(end, O["end"][k0 + bad[0]])
    H = px.h1
    a = int(np.searchsorted(H["start"], t_conf, "left"))
    b = int(np.searchsorted(H["start"], end, "left"))
    hit = np.flatnonzero(H["low"][a:b] <= story["target"] if sell else H["high"][a:b] >= story["target"])
    if len(hit):
        end = min(end, H["start"][a + hit[0]])
    return end


def _candidates(px, tf, story, sell, t_bo, t_conf, t_end):
    """Qualifying patterns on tf for this story, oldest first, plus counts of rejected ones."""
    cfg, P = px.cfg, px.P
    B = px.bars(tf)
    n = len(B["close"])
    kb = int(np.searchsorted(B["start"], t_bo, "right")) - 1  # entry bar holding the breakout candle start
    first = kb
    if cfg["skip_first"]:
        tops = [p[0] for p in px.piv(tf) if p[0] > kb and p[1] == ("H" if sell else "L")]
        if not tops:
            return [], {}
        first = tops[0]
    lows = [p for p in px.piv(tf) if p[1] == ("L" if sell else "H")]
    out, why = [], {"wide_stop": 0, "no_room": 0}
    for p in px.pats(tf, sell):
        c1, c4 = p["c1"], p["c1"] + 3
        if c1 <= first:
            continue
        act = max(B["end"][c4], t_conf)
        if act >= t_end:
            break
        entry = p["line"]
        stop = p["c3x"] + (1 if sell else -1) * cfg["stop_buffer_pips"] * P
        risk = (stop - entry) if sell else (entry - stop)
        if risk <= 0:
            continue
        if risk / P > cfg["max_stop_pips"] + 1e-9:
            why["wide_stop"] += 1
            continue
        tp2 = story["target"]
        r2 = ((entry - tp2) if sell else (tp2 - entry)) / risk
        if r2 < cfg["min_rr_tp2"]:
            why["no_room"] += 1
            continue
        # TP1: nearest unbroken entry-TF swing beyond tp1_min_rr R, known when c4 closed
        need = entry - cfg["tp1_min_rr"] * risk if sell else entry + cfg["tp1_min_rr"] * risk
        far = entry - cfg["tp1_max_rr"] * risk if sell else entry + cfg["tp1_max_rr"] * risk
        lv = []
        for q in lows:
            if q[3] > c4:
                break
            seg = B["close"][q[0] + 1:c4 + 1]
            if sell and far <= q[2] <= need and (not len(seg) or seg.min() > q[2]):
                lv.append(q[2])
            if not sell and need <= q[2] <= far and (not len(seg) or seg.max() < q[2]):
                lv.append(q[2])
        tp1 = (max(lv) if sell else min(lv)) if lv else need
        if (sell and tp1 < tp2) or (not sell and tp1 > tp2):
            tp1 = tp2
        exp = B["end"][min(c4 + cfg["retest_bars"], n - 1)]
        if c4 + cfg["retest_bars"] > n - 1:
            exp = np.datetime64("2262-01-01", "ns")  # still waiting at the end of the data
        out.append({"tf": tf, "entry": entry, "stop": stop, "tp1": float(tp1), "tp2": float(tp2),
                    "stop_pips": round(risk / P, 1), "R_tp1": round(abs(entry - tp1) / risk, 2),
                    "R_tp2": round(r2, 2), "c1_time": _s(B["start"][c1]), "active": act, "expires": exp})
    return out, why


def _walk(px, cands, sell, t_end):
    """Replace-with-newest pending order; return (filled pattern, fill H1 index) or (last, None)."""
    H = px.h1
    for j, c in enumerate(cands):
        stop_t = min(c["expires"], t_end)
        if j + 1 < len(cands):
            stop_t = min(stop_t, cands[j + 1]["active"])
        a = int(np.searchsorted(H["start"], c["active"], "left"))
        b = int(np.searchsorted(H["start"], stop_t, "left"))
        hit = np.flatnonzero(H["high"][a:b] >= c["entry"] if sell else H["low"][a:b] <= c["entry"])
        if len(hit):
            return c, a + int(hit[0])
    return cands[-1], None


def find_entry(px, story):
    cfg = px.cfg
    sell = story["side"] == "SELL"
    base = {"pair": px.pair, "story": story["story"], "side": story["side"], "tap_time": story["tap_time"],
            "confirm_time": story["confirm_time"], "story_target": story["target"]}
    if px.pair in cfg["avoid_pairs"]:
        return {**base, "status": "SKIPPED", "note": "avoided pair (spread)"}
    t_conf, t_bo = _t(story["confirm_time"]), _t(story["breakout_time"])
    t_end = _story_end(px, story, sell, t_conf, cfg["story_cfg"], cfg)
    notes = []
    for tf in cfg["entry_tfs"][story["story"]]:
        cands, why = _candidates(px, tf, story, sell, t_bo, t_conf, t_end)
        if why:
            notes.append(f"{tf}: wide_stop {why['wide_stop']}, no_room {why['no_room']}")
        if not cands:
            continue
        c, f = _walk(px, cands, sell, t_end)
        row = {**base, **{k: v for k, v in c.items() if k not in ("active", "expires")},
               "created_time": _s(c["active"]), "candidates": len(cands)}
        if f is not None:
            row.update(status="TRIGGERED", fill_time=_s(px.h1["start"][f]), _fill=f)
        elif min(c["expires"], t_end) > px.h1["end"][-1]:
            row.update(status="PENDING")
        else:
            row.update(status="MISSED")
        return row
    return {**base, "status": "NO_SETUP", "note": "; ".join(notes)}


def simulate(row, px):
    """TP1 and TP2 variants on H1 bars from the fill. Same bar stop+TP = loss; fill bar can only stop out."""
    if row.get("status") != "TRIGGERED":
        return row
    cfg, H = px.cfg, px.h1
    sell = row["side"] == "SELL"
    f = row.pop("_fill")
    e, s = row["entry"], row["stop"]
    risk = abs(s - e)
    t_cap = H["start"][f] + np.timedelta64(int(cfg["max_trade_bars"] * TF_HOURS[row["tf"]]), "h")
    j = int(np.searchsorted(H["start"], t_cap, "left"))  # first H1 bar past the holding time
    last = min(j, len(H["close"])) - 1
    for v in ("tp1", "tp2"):
        tp = row[v]
        res, out, k_exit = None, "timeout", last
        for k in range(f, last + 1):
            stop_hit = H["high"][k] >= s if sell else H["low"][k] <= s
            tp_hit = (H["low"][k] <= tp if sell else H["high"][k] >= tp) and k > f
            if stop_hit:
                res, out, k_exit = -1.0, "loss", k
                break
            if tp_hit:
                res, out, k_exit = abs(tp - e) / risk, "win", k
                break
        if res is None:
            res = ((e - H["close"][last]) if sell else (H["close"][last] - e)) / risk
            if j >= len(H["close"]) and H["end"][last] < t_cap:  # data ends before the holding time
                out = "open"
        row[f"{v}_outcome"], row[f"{v}_R"] = out, round(float(res), 2)
        row[f"{v}_exit_time"] = _s(H["start"][k_exit])
    return row


def find_entries(pair, h1, stories, cfg=None, story_cfg=None, sim=True):
    """Entry row per story (only CONFIRMED story rows, as from slk.story.find_stories)."""
    cfg = {**DEFAULT, "entry_tfs": ENTRY_TFS, **(cfg or {})}
    cfg["story_cfg"] = {**STORY_DEFAULT, **(story_cfg or {})}
    px = _Pair(pair, h1, cfg)
    out = []
    for st in stories:
        r = find_entry(px, st)
        r = simulate(r, px) if sim else r
        r.pop("_fill", None)
        out.append(r)
    return out
