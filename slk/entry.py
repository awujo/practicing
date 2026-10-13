"""Entry models (stage 2) after a CONFIRMED story. STRATEGY §3. Two models, row key `model`:

continuation (Kevin's "A series"), sell (a buy is the mirror image), on the entry timeframe, after the
story's external breakout:
  c1 bull + c2 bear  -> A-shape; thin line at the shared body price (c1 close)
  c3                 -> wick pokes up to the line (within tolerance) and the body closes back below it
  breakout           -> c4 OR ANY LATER candle, at most `breakout_max_bars` candles after c3: the first
                        impulsive bear candle closing below the lows of c1..(breakout-1) (internal BOS).
                        A candle closing back above the line before that kills the pattern.
  entry              -> sell limit at the line (retest); stop above the highest wick c3..(breakout-1) + buffer
  TP1                -> nearest unbroken entry-TF swing low between tp1_min_rr and tp1_max_rr R (else tp1_min_rr R)
  TP2                -> the story target

qmr = Quasimodo Reversal (Kevin's "B series"; Whisper heard "QMRO"), sell:
  on the entry TF close line: shoulder (swing high) -> neck (swing low) -> head (higher close than the
  shoulder = liquidity sweep) -> a body close below the neck. QMR zone = neck..shoulder (thin lines).
  No blind limit: price must come back into the zone and react, then a breakout on the trigger TF
  (`qmr_trigger_tf`, H1 under H4) = the continuation pattern above whose rejection reached the zone.
  Entry = retest of that trigger-TF line. Stop above the head (+ buffer) if that fits `max_stop_pips`,
  else above the trigger pattern's rejection wick (notes_entry §3: big zone -> stop on the rejecting candle).

Ranking: the most recent qualifying level replaces an older pending one, except that a pending QMR is
not replaced by a newer continuation level (QMR with rejection > breakout level with rejection). A pending
level that is not retested within `retest_bars` bars is MISSED (no chasing). Entries are taken on the
first entry TF of the ladder that has any qualifying setup (D story: H4 -> H2 -> H1).

Public:
  find_entries(pair, h1, stories, cfg)    -> one entry dict per story (status TRIGGERED/PENDING/MISSED/NO_SETUP/SKIPPED)
  simulate(entry, h1_bars, cfg)           -> TP1 / TP2 results in R on H1 bars (backtest)
"""
import numpy as np
import pandas as pd

from .candles import nominal_end, resample
from .story import DEFAULT as STORY_DEFAULT, STORIES, pip
from .structure import pivots, structural_swings

ENTRY_TFS = {"D": ("H4", "H2", "H1"), "W": ("D", "H4"), "M": ("W", "D")}

DEFAULT = {
    "tap_tol_pips": 1.0,       # c3 wick within this distance of the line counts as a touch (same as story)
    "impulse_mult": 1.0,       # breakout body >= this x average body of the previous `impulse_lookback` bars
    "impulse_lookback": 10,
    "stop_buffer_pips": 1.0,   # stop = rejection extreme (c3 .. breakout-1) + buffer
    "breakout_max_bars": 0,    # 0 = no limit (Kevin gives none): any later candle, until a close back through the line
    "max_stop_pips": 20.0,     # wider stop = pattern does not qualify (JPY pairs: same number of pips)
    "avoid_pairs": ["AUDNZD", "NZDCHF"],  # wide spread
    "retest_bars": 12,         # entry-TF bars after the breakout to wait for the retest, then MISSED
    "skip_first": True,        # no pattern formed at or before the top of the first retracement after the breakout
    "pivot": 2,                # close-line pivot order used for the first retracement and TP1 swing levels
    "tp1_min_rr": 1.5,
    "tp1_max_rr": 3.0,         # a swing level further than this is not TP1; TP1 falls back to tp1_min_rr R
    "min_rr_tp2": 1.0,         # story target must give at least this R from the entry
    "max_story_bars": None,    # origin bars after confirmation to look for entries (None = story max_hold)
    "max_trade_bars": 60,      # entry-TF bars a trade is held before it is closed at market
    "entry_models": ["continuation", "qmr"],
    "qmr_max_bars": 30,        # OUR CHOICE: QM-TF bars after the neck break for the zone reaction + trigger
    "alignment": "d_h4",       # setting entry_alignment: continuation entries only when D and H4 are in line (the
                               # CONFIRMED story = "daily reject daily" + the last H4 structural break the same way);
                               # w_d_h4 = also the last W structural break; off = no check
}
ALIGN_TFS = {"off": (), "d_h4": ("H4",), "w_d_h4": ("W", "H4")}
MODELS = ("continuation", "qmr")
# OUR CHOICE beyond Kevin's H4 -> 1H: QM on TF -> trigger TF (one or two steps lower)
QMR_TRIGGER_TF = {"H1": "H1", "H2": "H1", "H4": "H1", "D": "H4", "W": "D"}

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
    """All continuation patterns on bar arrays B. List of dicts: c1 index, line, c3x (rejection extreme
    c3..breakout-1, for the stop), bo (breakout bar index, c4 or later)."""
    o, h, l, c = B["open"], B["high"], B["low"], B["close"]
    n = len(c)
    if n < 4:
        return []
    tol = cfg["tap_tol_pips"] * P
    body = np.abs(c - o)
    lb = cfg["impulse_lookback"]
    avg = pd.Series(body).rolling(lb, min_periods=3).mean().shift(1).to_numpy()  # avg before each bar
    imp = np.nan_to_num(body >= cfg["impulse_mult"] * avg, nan=False).astype(bool)
    maxb = int(cfg.get("breakout_max_bars", 0) or 0)
    maxb = n if maxb <= 0 else maxb  # 0 = no limit
    i = np.arange(n - 3)
    i1, i2 = i + 1, i + 2
    lvl = c[i]
    if sell:
        ok = (c[i] > o[i]) & (c[i1] < o[i1])                                  # A-shape
        ok &= (h[i2] >= lvl - tol) & (c[i2] < lvl) & (h[i2] > np.maximum(o[i2], c[i2]))  # c3 wick rejection
    else:
        ok = (c[i] < o[i]) & (c[i1] > o[i1])                                  # V-shape
        ok &= (l[i2] <= lvl + tol) & (c[i2] > lvl) & (l[i2] < np.minimum(o[i2], c[i2]))
    out = []
    for k in np.flatnonzero(ok):
        line, c3 = float(c[k]), int(k) + 2
        ext = h[c3] if sell else l[c3]
        inner = l[k:c3 + 1].min() if sell else h[k:c3 + 1].max()
        for j in range(c3 + 1, min(c3 + maxb, n - 1) + 1):
            brk = (c[j] < o[j] and c[j] < inner) if sell else (c[j] > o[j] and c[j] > inner)
            if brk and imp[j]:
                out.append({"c1": int(k), "line": line, "c3x": float(ext), "bo": j})
                break
            if (c[j] > line) if sell else (c[j] < line):
                break  # closed back through the line before the breakout: not a rejection level
            ext = max(ext, h[j]) if sell else min(ext, l[j])
            inner = min(inner, l[j]) if sell else max(inner, h[j])
    return out


def qm_structures(B, piv, sell, max_bars):
    """Quasimodo structures on bar arrays B from close-line pivots (sell; buy mirrored): consecutive pivots
    shoulder H -> neck L -> head H with head close > shoulder close, then the first body close below the neck
    within `max_bars` bars of the head and before any close above the head. Returns dicts with indexes and
    prices; head_x = highest wick neck..break (stop side)."""
    c, h, l = B["close"], B["high"], B["low"]
    n = len(c)
    out = []
    a_k, b_k = ("H", "L") if sell else ("L", "H")
    for a, b, d in zip(piv, piv[1:], piv[2:]):
        if (a[1], b[1], d[1]) != (a_k, b_k, a_k):
            continue
        sh, nk, hd = a[2], b[2], d[2]
        if not ((hd > sh > nk) if sell else (hd < sh < nk)):
            continue
        brk = None
        for j in range(d[0] + 1, min(d[0] + max_bars, n - 1) + 1):
            if (c[j] > hd) if sell else (c[j] < hd):
                break
            if (c[j] < nk) if sell else (c[j] > nk):
                brk = j
                break
        if brk is None:
            continue
        hx = h[b[0]:brk + 1].max() if sell else l[b[0]:brk + 1].min()
        out.append({"shoulder_i": a[0], "neck_i": b[0], "head_i": d[0], "brk": brk, "shoulder": float(sh),
                    "neck": float(nk), "head": float(hd), "head_x": float(hx)})
    return out


class _Pair:
    """Per-pair cache of resampled bars, pivots and patterns."""

    def __init__(self, pair, h1, cfg):
        self.pair, self.cfg, self.P = pair, cfg, pip(pair)
        self.h1 = _arrays(resample(h1, "H1"))
        self._bars, self._piv, self._pat, self._qm, self._brk = {}, {}, {}, {}, {}
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

    def last_break(self, tf, t):
        """Direction ('up' / 'down' / None) of the last structural break (STRATEGY §1: a close beyond the last
        close-line swing, story swing_pivot) on tf known at time t (that bar closed by t)."""
        if tf not in self._brk:
            from .story import _breaks  # noqa: PLC0415 (story imports nothing from entry)
            B = self.bars(tf)
            end = B["end"].copy()
            if tf in ("D", "W", "M") and len(end):  # a still-forming last bar is not closed (live data)
                end[-1] = max(end[-1], np.datetime64(nominal_end(pd.Timestamp(B["start"][-1], tz="UTC"), tf)
                                                     .tz_convert(None), "ns"))
            c = B["close"]
            br = _breaks(structural_swings(c, pivots(c, self.cfg["story_cfg"]["swing_pivot"])))
            self._brk[tf] = (np.array([end[i] for i, _, _ in br], dtype="datetime64[ns]"), [u for _, u, _ in br])
        when, ups = self._brk[tf]
        j = int(np.searchsorted(when, t, "right")) - 1
        return None if j < 0 else ("up" if ups[j] else "down")

    def aligned(self, sell, t, mode):
        """entry_alignment: the story itself is the confirmed origin-TF bias (D reject D); d_h4 adds the last H4
        structural break in the story direction [T entry-4@1670-1690, entry3@696-818], w_d_h4 also the last W
        break [T weekly-recap@151-282, story-line@304-322]. Checked at time t (the pattern's breakout close)."""
        want = "down" if sell else "up"
        return all(self.last_break(tf, t) == want for tf in ALIGN_TFS.get(mode or "off", ()))

    def qms(self, tf, sell):
        if (tf, sell) not in self._qm:
            self._qm[(tf, sell)] = qm_structures(self.bars(tf), self.piv(tf), sell, self.cfg["qmr_max_bars"])
        return self._qm[(tf, sell)]


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


def _setup(px, tf, story, sell, entry, stop, bo, t_conf, why, extra):
    """Entry candidate from a line on tf (breakout bar `bo`), or None (counted in `why`). TP1 = nearest
    unbroken tf swing beyond tp1_min_rr R known when the breakout closed; TP2 = story target."""
    cfg, P = px.cfg, px.P
    B = px.bars(tf)
    n = len(B["close"])
    risk = (stop - entry) if sell else (entry - stop)
    if round(risk / P, 1) <= 0:  # stop on (or within 0.05 pip of) the entry: no stop at all
        return None
    if risk / P > cfg["max_stop_pips"] + 1e-9:
        why["wide_stop"] += 1
        return None
    tp2 = story["target"]
    r2 = ((entry - tp2) if sell else (tp2 - entry)) / risk
    if r2 < cfg["min_rr_tp2"]:
        why["no_room"] += 1
        return None
    need = entry - cfg["tp1_min_rr"] * risk if sell else entry + cfg["tp1_min_rr"] * risk
    far = entry - cfg["tp1_max_rr"] * risk if sell else entry + cfg["tp1_max_rr"] * risk
    lv = []
    for q in px.piv(tf):
        if q[3] > bo:
            break
        if q[1] != ("L" if sell else "H"):
            continue
        seg = B["close"][q[0] + 1:bo + 1]
        if sell and far <= q[2] <= need and (not len(seg) or seg.min() > q[2]):
            lv.append(q[2])
        if not sell and need <= q[2] <= far and (not len(seg) or seg.max() < q[2]):
            lv.append(q[2])
    tp1 = (max(lv) if sell else min(lv)) if lv else need
    if (sell and tp1 < tp2) or (not sell and tp1 > tp2):
        tp1 = tp2
    exp = B["end"][min(bo + cfg["retest_bars"], n - 1)]
    if bo + cfg["retest_bars"] > n - 1:
        exp = np.datetime64("2262-01-01", "ns")  # still waiting at the end of the data
    return {"tf": tf, "entry": entry, "stop": stop, "tp1": float(tp1), "tp2": float(tp2),
            "stop_pips": round(risk / P, 1), "R_tp1": round(abs(entry - tp1) / risk, 2),
            "R_tp2": round(r2, 2), "active": max(B["end"][bo], t_conf), "expires": exp, **extra}


def _candidates(px, tf, story, sell, t_bo, t_conf, t_end):
    """Qualifying continuation patterns on tf for this story, oldest first, plus counts of rejected ones."""
    cfg, P = px.cfg, px.P
    B = px.bars(tf)
    kb = int(np.searchsorted(B["start"], t_bo, "right")) - 1  # entry bar holding the breakout candle start
    first = kb
    if cfg["skip_first"]:
        tops = [p[0] for p in px.piv(tf) if p[0] > kb and p[1] == ("H" if sell else "L")]
        if not tops:
            return [], {}
        first = tops[0]
    out, why = [], {"wide_stop": 0, "no_room": 0}
    for p in px.pats(tf, sell):
        if p["c1"] <= first:
            continue
        if max(B["end"][p["bo"]], t_conf) >= t_end:
            break
        stop = p["c3x"] + (1 if sell else -1) * cfg["stop_buffer_pips"] * P
        c = _setup(px, tf, story, sell, p["line"], stop, p["bo"], t_conf, why,
                   {"model": "continuation", "c1_time": _s(B["start"][p["c1"]]),
                    "bo_candle": p["bo"] - p["c1"] + 1})
        if c:
            out.append(c)
    return out, why


def _qmr_candidates(px, tf, story, sell, t_conf, t_end):
    """QMR setups: QM on tf (neck broken after the tap), price back in the shoulder/neck zone with a
    trigger-TF continuation pattern whose rejection reached the zone; the first one per QM. The trigger TF
    is never below the story's lowest entry TF (W story: QM on H4 triggers on H4)."""
    cfg, P = px.cfg, px.P
    B = px.bars(tf)
    ttf = cfg.get("qmr_trigger_tf", QMR_TRIGGER_TF).get(tf, tf)
    low = min(cfg["entry_tfs"][story["story"]], key=TF_HOURS.get)
    if TF_HOURS[ttf] < TF_HOURS[low]:
        ttf = low
    T = px.bars(ttf)
    tol, buf = cfg["tap_tol_pips"] * P, cfg["stop_buffer_pips"] * P
    t_tap = _t(story["tap_time"])
    out, why = [], {"wide_stop": 0, "no_room": 0}
    pats = px.pats(ttf, sell)
    c1s = np.array([p["c1"] for p in pats], dtype=int)
    for q in px.qms(tf, sell):
        t_brk = B["end"][q["brk"]]
        if t_brk <= t_tap or t_brk >= t_end:
            continue
        lim = q["brk"] + cfg["qmr_max_bars"]
        t_lim = B["end"][lim] if lim < len(B["end"]) else np.datetime64("2262-01-01", "ns")
        k0 = int(np.searchsorted(T["start"], t_brk, "left"))   # first trigger bar after the neck break
        cl = T["close"][k0:]
        bad = np.flatnonzero(cl > q["head"] if sell else cl < q["head"])
        k_bad = k0 + int(bad[0]) if len(bad) else len(T["close"])  # close beyond the head kills the QM
        for p in pats[int(np.searchsorted(c1s, k0, "left")):]:
            if p["bo"] >= k_bad or T["end"][p["bo"]] > t_lim or max(T["end"][p["bo"]], t_conf) >= t_end:
                break
            if (p["c3x"] < q["neck"] - tol) if sell else (p["c3x"] > q["neck"] + tol):
                continue  # this trigger-TF level did not react inside the QMR zone
            entry = p["line"]
            head_stop = q["head_x"] + buf if sell else q["head_x"] - buf
            pat_stop = p["c3x"] + buf if sell else p["c3x"] - buf
            stop = head_stop if abs(head_stop - entry) / P <= cfg["max_stop_pips"] + 1e-9 else pat_stop
            c = _setup(px, ttf, story, sell, entry, stop, p["bo"], t_conf, why,
                       {"model": "qmr", "c1_time": _s(T["start"][p["c1"]]), "bo_candle": p["bo"] - p["c1"] + 1,
                        "qm_tf": tf, "qm_shoulder": q["shoulder"], "qm_neck": q["neck"], "qm_head": q["head"],
                        "stop_at": "head" if stop == head_stop else "rejection"})
            if c:
                out.append(c)
            break
    return out, why


def _walk(px, cands, sell, t_end):
    """Pending-order walk, oldest first. A newer level replaces the pending one, except that a pending QMR is
    kept over a newer continuation level (QMR ranks higher). Returns (filled, H1 index) or (last pending, None)."""
    H = px.h1

    def fill(c, upto):
        a = int(np.searchsorted(H["start"], c["active"], "left"))
        b = int(np.searchsorted(H["start"], min(upto, c["expires"], t_end), "left"))
        hit = np.flatnonzero(H["high"][a:b] >= c["entry"] if sell else H["low"][a:b] <= c["entry"])
        return a + int(hit[0]) if len(hit) else None

    cur = None
    for c in sorted(cands, key=lambda x: x["active"]):
        if cur is not None:
            f = fill(cur, c["active"])
            if f is not None:
                return cur, f
            pending = c["active"] < min(cur["expires"], t_end)
            if pending and cur["model"] == "qmr" and c["model"] == "continuation":
                continue
        cur = c
    f = fill(cur, t_end)
    return cur, f


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
    models = cfg.get("entry_models") or MODELS
    mode = cfg.get("alignment") or "off"
    for tf in cfg["entry_tfs"][story["story"]]:
        cands = []
        for m in models:
            got, why = (_candidates(px, tf, story, sell, t_bo, t_conf, t_end) if m == "continuation"
                        else _qmr_candidates(px, tf, story, sell, t_conf, t_end))
            if m == "continuation" and mode != "off":
                n0 = len(got)
                got = [c for c in got if px.aligned(sell, c["active"], mode)]
                if n0 > len(got):
                    notes.append(f"{tf}: {n0 - len(got)} continuation not aligned ({mode})")
            cands += got
            if why:
                notes.append(f"{tf}{'' if m == 'continuation' else ' ' + m}: wide_stop {why['wide_stop']}, no_room {why['no_room']}")
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
