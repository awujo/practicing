"""The story line (bias): tap-reject-close on the origin TF, breakout of point B one TF lower. STRATEGY §2.

Rules built here (each story dict carries `rule`, and `end_reason` once it is over):
  standard     key-level tap-reject-close + confirm-TF body close beyond point B (the external break)
  sweep_start  the same after a wick sweep of the previous origin candle's high/low (no key level)
  flip         a new story that started when the previous one ended early by a flip (#29)
  alignment    W close beyond the last W swing -> D close beyond the last D swing -> H4 break, same way (#31b)
  cadjpy       W trend + D sweep of the previous-day low/high INTO a D open-close level, close back: confirmed at
               the D close without an H4 breakout (#31c)
  Labels on every story (no effect on the outcome): next_day (Next Day Rule; None for cadjpy = no breakout),
  retrace (a later confirm-TF candle of the breakout's origin bar closed back beyond B, Kevin qns-pt2@1946-2030),
  level_time (start of the origin candle at whose close the level was known, i.e. "formed").
  "+overlap"   appended when the origin level is also a fresh higher-TF level rejected by a CLOSED higher-TF
               candle (#31a): the take profit is the next key level ("we take our profit at this key level").
"""
import numpy as np
import pandas as pd

from .candles import nominal_end, resample
from .levels import Level, find_levels, run_levels, sweep_taps
from .structure import SwingBook, pivots, structural_swings, swings, trend

STORIES = {"M": ("M", "W"), "W": ("W", "D"), "D": ("D", "H4")}
HIGHER = {"D": "W", "W": "M", "M": None}
HIGHER_ALL = {"D": ("W", "M"), "W": ("M",), "M": ()}

DEFAULT = {
    "level_pivot": 1,       # A/V must be a close-line turning point of this order
    "swing_pivot": 2,       # close-line turning points that can become structural swings (trend, targets)
    "b_pivot": 1,           # point B = last close-line V/A turn of this order on the confirm TF before the tap
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
    "sweep_start": True,    # alternative start without a key level: wick sweep of the previous origin candle's
                            # high/low + close back inside [T story-line-pt3@1887-2010, pt4@1349-1500]
    # --- REVIEW #26, #29, #30, #31 (STRATEGY v0.6) ---
    "most_recent_level": True,  # #26 only the most recent fresh trend level formed before the tap counts
    "flip_end": True,       # #29 a D KL on the way rejected the other way + H4 break the other way ends the story
    "htf_targets": True,    # #30 target = next opposite fresh KL of the same OR a higher TF, or ERL
    "overlap_rule": True,   # #31a origin KL shared with a (closed, rejected) higher-TF KL -> TP at the next KL
    "overlap_tol_pips": 3.0,  # OUR CHOICE: two TF levels within this distance are "the same spot"
    "alignment_start": True,  # #31b W BOS -> D BOS -> H4 BOS the same way = a D continuation story
    "cadjpy_exception": True,  # #31c W trend + D sweep of the previous day low/high into a D OC level, close back
    # Next Day Rule [T story-line-pt3@1358-1401 "you go to four hours after the close of this day, you just see a
    # clean breakout"; qns-pt2@1946-1962 "the next day ... not that particular day"]: the confirm-TF breakout should
    # come from a candle that opens after the origin (tap/rejection) candle closed. "flag" = every story carries
    # next_day True/False (label only); "require" = a story whose breakout is inside the rejection candle is dropped.
    "next_day_rule": "flag",
}
# Point B is broken only by an EXTERNAL break: a confirm-TF body close beyond B, the last opposite swing before
# the first tap (+ same_bar_close). Kevin's two confirmations, "sweep and break" (advanced structure: sweep of
# liquidity, then BOS) or a plain "breakout" [T story-line-pt2@297-441, 571-647], both end in that same close
# beyond the last V/A before the tap [F frames_D story-line-pt2 sheet_001-021 + Corrections: "BMS" (sweep+break)
# and "BO" are both a body close through the last A/V before the tap]; the sweep only
# labels which one it was (story["break_kind"]). Internal breaks (BOS after the tap) never confirm the bias;
# they are for continuation entries only (slk/entry.py). Deliberately no setting changes this, except Kevin's own
# CADJPY exception (#31c, `cadjpy_exception`) [T cadjpy-bd@940-995: "you really do not need to be waiting for this
# breakout again ... the weekly is bullish and the daily just bullish and there's a very obvious target"].


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
    X = _Ctx(pair, h1, story, cfg)
    aligns = X.align_starts() if cfg["alignment_start"] and story == "D" else {}
    rows, busy_until, forced = [], -1, {}
    for bar in sorted(set(X.taps) | set(aligns)):
        if bar <= busy_until or bar < 2:
            continue
        tr = trend(X.osw.at(bar - 1), X.O["close"][bar - 1])
        r = None
        if bar in forced:  # #29: the level that ended the previous story starts the opposite one
            r = X.start(forced.pop(bar), bar, "flip", tr)
        if r is None and bar in X.taps:
            lv = X.choose(bar, tr)
            if lv is not None:
                r = X.start(lv, bar, "sweep_start" if lv.kind == "sweep" else "standard", tr)
        if r is None and bar in aligns:
            r = X.start(aligns[bar], bar, "alignment", tr)
        if r is None:
            continue
        rows.append(r)
        busy_until = r.pop("_busy")
        fl = r.pop("_flip", None)
        if fl is not None:
            forced[fl[0]] = fl[1]
    return rows


def _structure(bars, cfg):
    """Structural swings of the close line (trend, targets): STRATEGY §1, slk/structure.structural_swings."""
    c = bars["close"].to_numpy()
    return structural_swings(c, pivots(c, cfg["swing_pivot"]))


def _taps(levels, ob, cfg):
    """origin bar -> levels tapped (wick in, close back) on it; plus the alternative start (sweep of the
    previous origin candle's high/low) when cfg['sweep_start']."""
    taps = {}
    for lv in levels:
        for b, kind, _ in lv.events:
            if kind == "tap":
                taps.setdefault(b, []).append(lv)
    if cfg.get("sweep_start"):
        for lv in sweep_taps(ob):
            taps.setdefault(lv.born, []).append(lv)
    return taps


def _pick(cands):
    """Most recent fresh key level; the sweep start only when no key level was tapped on that bar ("sometimes
    there will not be any key level" [T story-line-pt3@1887-1917]); a sweep INTO a key level is that level's tap."""
    kl = [x for x in cands if x.kind != "sweep"]
    return max(kl or cands, key=lambda x: x.born)


def _point_b(sw, k0, sell):
    """Point B: the last confirm-TF close-line V-shape (sell) / A-shape (buy) made BEFORE the first touch bar k0
    [T story-line-pt3@1690-1790; F story-line-pt2/sheet_015 t=1140-1180: CADJPY 4H line chart, ray at the last
    small peak ~113.2 just before the tap]. `sw` = swings known at the close of k0 (the touch bar's close may
    complete a turn made at k0-1); the rejection's own swing (index >= k0) never counts."""
    want = "L" if sell else "H"
    for s in reversed(sw):  # swings are in bar order: the last matching one before k0 (= the old list's [-1])
        if s[1] == want and s[0] < k0:
            return s[2]
    return None


def _htf_trend(hb, hpiv, t):
    """Trend of the higher TF on its last bar closed before time t."""
    hi = np.searchsorted(hb["start"].to_numpy(), t, side="right") - 2  # last closed HTF bar
    return trend(swings(hpiv, hi), hb["close"].iat[hi]) if hi >= 2 else "range"


def _against(side, htf_trend):
    return (side == "sell" and htf_trend == "up") or (side == "buy" and htf_trend == "down")


def _r(x):
    return None if x is None else round(float(x), 5)


class _LevelSet:
    """Key levels of one timeframe with fast 'fresh at bar i' lookups."""

    def __init__(self, bars, levels, tf=None):
        self.start, self.end = bars["start"].to_numpy(), bars["end"].to_numpy().copy()
        if tf in ("D", "W", "M") and len(self.end):
            # the last bar may still be forming (live: data cut at the last closed ORIGIN bar, mid-week): its
            # 'end' is then only the last hour seen, so it would look closed. Use the bar's nominal close.
            self.end[-1] = max(self.end[-1], nominal_end(self.start[-1], tf))
        self.levels = levels
        self.buy = np.array([lv.side == "buy" for lv in levels], dtype=bool)
        self.born = np.array([lv.born for lv in levels], dtype=np.int64)
        self.first = np.array([lv.events[0][0] if lv.events else np.iinfo(np.int64).max for lv in levels],
                              dtype=np.int64)
        self.first_tap = np.array([bool(lv.events) and lv.events[0][1] == "tap" for lv in levels], dtype=bool)

    def fresh_prices(self, buy, upto):
        """Prices of levels of this side born by bar `upto` with no event (tap/break) up to that bar, in order."""
        m = (self.buy == buy) & (self.born <= upto) & (self.first > upto)
        return [self.levels[i].price for i in np.flatnonzero(m)]

    def closed_upto(self, t):
        """Index of the last bar of this TF closed at time t (-1 if none)."""
        return int(np.searchsorted(self.end, t, "right")) - 1


class _Ctx:
    """Everything one story run needs (bars, levels, swings, caches). Speed caches give the same results as the
    plain loops: swing lists by `upto`, first event bar of each level, first confirm bar of each origin bar."""

    def __init__(self, pair, h1, story, cfg):
        self.cfg, self.story, self.pair = cfg, story, pair
        otf, ctf = STORIES[story]
        self.otf, self.ctf = otf, ctf
        ob, cb = resample(h1, otf), resample(h1, ctf)
        self.P = pip(pair)
        self.tol = cfg["tap_tol_pips"] * self.P
        self.levels = run_levels(ob, find_levels(ob, cfg), self.tol)
        self.lv = _LevelSet(ob, self.levels)
        self.osw, self.csw = SwingBook(_structure(ob, cfg)), SwingBook(pivots(cb["close"], cfg["b_pivot"]))
        self.O = {k: ob[k].to_numpy() for k in ("open", "high", "low", "close")}
        self.C = {k: cb[k].to_numpy() for k in ("open", "high", "low", "close")}
        self.o_start, self.o_end = ob["start"].to_numpy(), ob["end"].to_numpy()
        self.c_start, self.c_end = cb["start"].to_numpy(), cb["end"].to_numpy()
        self.c2o = np.searchsorted(self.o_start, self.c_start, side="right") - 1  # origin bar of each confirm bar
        n = len(self.O["close"])
        self.first_k = np.searchsorted(self.c2o, np.arange(n + 1), "left")  # first confirm bar of origin bar i
        self.htf = HIGHER[story]
        self.hb = resample(h1, self.htf) if self.htf else None
        if self.htf:
            self.h_start, self.h_close = self.hb["start"].to_numpy(), self.hb["close"].to_numpy()
            self.hsw = SwingBook(_structure(self.hb, cfg))
        self.higher = []  # [(tf, _LevelSet)] next higher TF first
        if cfg["htf_targets"] or cfg["overlap_rule"]:
            for tf in HIGHER_ALL[story]:
                hb = self.hb if tf == self.htf else resample(h1, tf)
                self.higher.append((tf, _LevelSet(hb, run_levels(hb, find_levels(hb, cfg), self.tol), tf)))
        self.taps = _taps(self.levels, ob, cfg)
        self._bs = {}       # break_search memo
        self._flips = None  # lazy: break bars of opposite levels (CADJPY precondition)

    # ------------------------------------------------------------------ choosing the start
    def htf_trend(self, t):
        """= _htf_trend(hb, hpiv, t)."""
        hi = np.searchsorted(self.h_start, t, side="right") - 2
        return trend(self.hsw.at(hi), self.h_close[hi]) if hi >= 2 else "range"

    def most_recent_ok(self, lv, bar):
        """#26 [T story-line-pt2@897-1000: "you place your mark at the most recent one ... the nearest fresh key
        level ... we just remove everything and mark that last one"; F story-line-pt2/sheet_013-016 (CADJPY: three
        candidate levels, the most recent fresh one kept, the stale ones removed)]: the tapped level must be the most
        recent fresh level of its side that existed BEFORE the tap (born <= tap bar, untouched before it). An older
        level tapped while a newer fresh one exists is ignored; levels formed after the tap never count."""
        if lv.kind in ("sweep", "align"):
            return True
        L = self.lv
        # fresh before the tap bar; a newer level closed through ON the tap bar failed ("abused", not fresh), so
        # only a newer level tapped (wick in, close back) on that bar still outranks the tapped one
        m = (L.buy == (lv.side == "buy")) & (L.born <= bar) & ((L.first > bar) | ((L.first == bar) & L.first_tap))
        return not m.any() or lv.born >= L.born[m].max()

    def choose(self, bar, tr):
        """Level tapped on `bar` that starts a story (trend filter, most recent fresh level), or None."""
        cfg = self.cfg
        if cfg["trend_filter"]:
            if tr == "range":
                return None
            cands = [lv for lv in self.taps[bar] if lv.side == ("sell" if tr == "down" else "buy")]
        else:
            cands = self.taps[bar]
        if not cands:
            return None
        lv = _pick(cands)
        if cfg["most_recent_level"] and not self.most_recent_ok(lv, bar):
            sw = [x for x in cands if x.kind == "sweep"]  # a stale level is no key level: the sweep start may apply
            return sw[0] if sw else None
        return lv

    def cadjpy(self, lv, bar, h_tr):
        """#31c CADJPY exception [T cadjpy-bd@400-760 ("price did a sweep of previous day low into the daily open
        close level, when we are already bullish on the weekly ... direction is confirmed"), 940-995 ("you really do
        not need to be waiting for this breakout again"); F cadjpy-bd/sheet_008-009 (short line ~113.2 on the open-
        close level, next candle wicks below the previous day low and closes above, line "target" 114.466 drawn at
        once)]: D story, higher-TF (W) trend in the story direction, the tap candle's wick sweeps the previous day's
        low (high for a sell) INTO a D open-close level (or the flipped zone, as in his example) and the candle
        closes back above the previous low and the level. Confirmed at that D close, no H4 breakout needed.
        Precondition (Validation 4): the daily has ALREADY flipped the story's way: "after the bullish close above
        this guy, price did a sweep of previous day low" / "weekly is bullish and now daily has flipped the zone"
        [T cadjpy-bd@440-560, 680-720; F cadjpy-bd/sheet_008: the big bull D candle closes above the D sell zone,
        the sweep comes 1-2 candles later] = a D body close through an OPPOSITE key level within `max_wait` D bars
        before the sweep. Without it this is an ordinary tap and the H4 breakout is required."""
        if not self.cfg["cadjpy_exception"] or self.story != "D" or lv.kind not in ("OC", "flip") or bar < 1:
            return False
        if not self.flipped_before(lv.side, bar):
            return False
        O = self.O
        if lv.side == "buy":
            return h_tr == "up" and O["low"][bar] < O["low"][bar - 1] and O["close"][bar] > O["low"][bar - 1]
        return h_tr == "down" and O["high"][bar] > O["high"][bar - 1] and O["close"][bar] < O["high"][bar - 1]

    def flipped_before(self, side, bar):
        """True when an opposite key level (sell levels for a buy) was broken by an origin body close in the
        `max_wait` bars before `bar` (the daily flipped that way)."""
        if self._flips is None:
            self._flips = {k: np.array(sorted(b for lv in self.levels if lv.side != k and lv.kind != "sweep"
                                              for b, kind, _ in lv.events if kind == "break"), dtype=np.int64)
                           for k in ("buy", "sell")}
        b = self._flips[side]
        i = int(np.searchsorted(b, bar, "left"))  # breaks strictly before the tap bar
        return i > 0 and b[i - 1] >= bar - self.cfg["max_wait"]

    def overlap(self, lv, bar, t_conf):
        """#31a [T all-in-1@1424-1620 ("two timeframes overlap ... weekly and daily are using exactly this key level
        ... it becomes daily reject daily ... we go to four hours for break out ... instead of swing it to here, we
        take our profit at this key level"); F all-in-1/sheet_020-026 (EURGBP: weekly V = daily V ~0.8657, TP at the
        next KL 0.8722); F cadjpy-bd/sheet_014-017 + T cadjpy-bd@811-905 ("for it to overlap it needs to be on the
        same spot ... must be on a fresh level"); T qns-pt2 / F qns-pt2 (a weekly tap is judged after the weekly
        close)]: the origin level is also a fresh level of the next higher TF (within overlap_tol_pips, same side),
        that higher-TF candle tapped it (first touch) and has CLOSED back on the rejection side by confirmation."""
        if not self.cfg["overlap_rule"] or not self.higher or lv.kind in ("sweep", "align"):
            return False
        _, H = self.higher[0]
        hi = int(np.searchsorted(H.start, self.o_start[bar], "right")) - 1
        if hi < 0 or H.end[hi] > t_conf:
            return False  # the higher-TF candle is still open: judged only after its close
        tol = self.cfg["overlap_tol_pips"] * self.P
        for L in H.levels:
            if (L.side == lv.side and abs(L.price - lv.price) <= tol and L.events and L.events[0][0] == hi
                    and L.events[0][1] == "tap"):
                return True
        return False

    # ------------------------------------------------------------------ confirmation
    def break_search(self, lv, bar):
        """Point B before the first touch and the external break of it (same rules as before #26-#31).
        Returns (k0, B, swings at k0, breakout confirm-bar index) or None. Memoised per (level, bar): flip_scan
        asks again for the same opposite taps (pure function of the context)."""
        key = (id(lv), bar)
        if key not in self._bs:
            self._bs[key] = self._break_search(lv, bar)
        return self._bs[key]

    def _break_search(self, lv, bar):
        cfg, O, C, c2o = self.cfg, self.O, self.C, self.c2o
        sell = lv.side == "sell"
        tol = self.tol
        # first confirm-TF bar inside the tap bar that touched the level = "price first tapped"
        ks = np.arange(self.first_k[bar], self.first_k[bar + 1])
        if not len(ks):
            return None
        touch = [k for k in ks if (C["high"][k] >= lv.price - tol if sell else C["low"][k] <= lv.price + tol)]
        k0 = touch[0] if touch else ks[0]
        sw = self.csw.at(k0)
        B = _point_b(sw, k0, sell)
        if B is None:
            return None
        if (sell and B >= lv.price) or (not sell and B <= lv.price):
            return None
        last_o = min(bar + cfg["max_wait"], len(O["close"]) - 1)
        retaps, k, brk = 0, k0, None
        while k < len(C["close"]) and c2o[k] <= last_o:
            oi = c2o[k]
            if oi > bar and k == self.first_k[oi]:  # new origin bar starts: judge the previous one
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
                k = self.first_k[oi + 1]  # cancelled for this day; try from the next one
                continue
            k += 1
        if brk is None:
            return None
        if cfg["next_day_rule"] == "require" and c2o[brk] <= bar:
            return None  # same-day breakout (inside the rejection candle): Next Day Rule required
        return k0, B, sw, brk

    def conf_index(self, brk, bar):
        """Confirm-TF bar at whose close the story is known: the breakout bar and the tap bar have closed, and
        (same_bar_close) the origin bar holding the breakout too: its close beyond B was used (no look-ahead)."""
        c_end = self.c_end
        need_end = self.o_end[self.c2o[brk]] if self.cfg["same_bar_close"] else self.o_end[bar]
        k = brk
        while k + 1 < len(c_end) and c_end[k] < need_end:
            k += 1
        return k

    def target(self, sell, closed_o, t, ref, mode="nearest"):
        """#30 [T story-line@648 (monthly story -> next monthly fresh level), story-line-pt2@1914-1968; F story-line-
        pt2/sheet_025-028 (CADJPY TP = previous D high 114.65); T class-wrok@480-620 (H4 story on a level shared
        with D: TP at the next H4 level, never swung past the stronger opposing daily zone)]: nearest of the
        opposite fresh key levels of the origin TF and every HIGHER TF (each as of its last closed bar), and the
        origin-TF structural swings (ERL). Nearest = the TP is capped at the next level of the weaker TF.
        mode 'kl' (overlap): next key level, ERL only if none; mode 'erl' (CADJPY "previous high"): ERL first."""
        kls = self.lv.fresh_prices(sell, closed_o)  # opposite side: buy levels for a sell
        if self.cfg["htf_targets"]:
            for _, H in self.higher:
                kls += H.fresh_prices(sell, H.closed_upto(t))
        erl = [s[2] for s in self.osw.at(closed_o) if s[1] == ("L" if sell else "H")]
        beyond = lambda xs: [x for x in xs if (x < ref if sell else x > ref)]  # noqa: E731
        near = lambda xs: (max(xs) if sell else min(xs)) if xs else None  # noqa: E731
        kls, erl = beyond(kls), beyond(erl)
        if mode == "kl" and kls:
            return near(kls)
        if mode == "erl" and erl:
            return near(erl)
        return near(kls + erl)

    def start(self, src, bar, rule, tr):
        """One story from a tap/sweep/alignment start on origin bar `bar` (None if it never confirms)."""
        cfg = self.cfg
        lv, pre = (src[0], src[1:]) if isinstance(src, tuple) else (src, None)
        h_tr = self.htf_trend(self.o_start[bar]) if self.htf else None
        if cfg["htf_filter"] and _against(lv.side, h_tr):
            return None
        if pre is not None:  # alignment: B and breakout found by align_starts
            B, brk = pre
            kind = "breakout"
        elif rule == "standard" and self.cadjpy(lv, bar, h_tr):
            rule, B, brk, kind = "cadjpy", lv.price, int(self.first_k[bar + 1]) - 1, "none"
            if brk < self.first_k[bar]:
                return None
        else:
            b = self.break_search(lv, bar)
            if b is None:
                return None
            k0, B, sw, brk = b
            kind = _break_kind(lv.side == "sell", sw, k0, brk, self.C)
        r = self.finish(lv, bar, B, brk, kind, rule)
        if r is None:
            return None
        r.update(pair=self.pair, story=self.story, trend=tr, level_kind=lv.kind, level=lv.price,
                 tap_time=str(self.o_start[bar])[:16], level_time=self.level_time(lv, bar),
                 next_day=None if kind == "none" else bool(self.c2o[brk] > bar))
        if self.htf:
            r["htf_trend"] = h_tr
        return r

    def level_time(self, lv, bar):
        """Start of the origin candle at whose close the level was known ("formed"); the tap bar for a sweep."""
        i = bar if lv.kind == "sweep" else min(max(int(lv.born) - 1, 0), bar)
        return str(self.o_start[i])[:16]

    def retrace(self, sell, B, brk):
        """Kevin [T qns-pt2@1946-2030]: the breakout day "should not trade back into the breakout zone", if it does
        it is "no longer high probability". True when a later confirm-TF candle of the origin bar holding the
        breakout closes back at or beyond B (above for a sell). Known at that origin bar's close (= confirmation
        with same_bar_close). Label only: the D close back through B (same_bar_close) is the cancel rule."""
        ks = range(brk + 1, int(self.first_k[self.c2o[brk] + 1]))
        c = self.C["close"]
        return bool(any((c[k] >= B) if sell else (c[k] <= B) for k in ks))

    def flip_scan(self, lv, target, closed_o, end_o):
        """#29 [T story-line-pt2@1779-1869: "the moment we tap on another daily key level before the zone we are
        expecting price to come into, the moment price closes below it and then gives us a breakout in four hours,
        it means that that daily has flipped"; "if we don't get a rejection and a breakout to the downside ... we are
        still bullish"; F story-line-pt2/sheet_023 (CADJPY D: levels 113.946 / 113.49 between the origin 112.903 and
        the target ~114.65, sketch of a rejection there and a drop)]: the earliest opposite fresh origin-TF key level
        between the origin level and the target, tapped-rejected-closed after the confirmation, whose own point B
        then breaks on the confirm TF (same external-break rules). Returns (conf index, tap bar, level, B) or None."""
        sell = lv.side == "sell"
        best = None
        for o in range(closed_o + 1, end_o + 1):
            for f in self.taps.get(o, ()):
                if f.kind == "sweep" or (f.side == "sell") == sell:
                    continue
                if not ((target < f.price < lv.price) if sell else (lv.price < f.price < target)):
                    continue  # not on the way to the target
                b = self.break_search(f, o)
                if b is None:
                    continue
                ck = self.conf_index(b[3], o)
                if best is None or (ck, -f.born) < (best[0], -best[2].born):  # earliest; then most recent level
                    best = (ck, o, f, b[1])
        return best

    def finish(self, lv, bar, B, brk, kind, rule):
        cfg, O, C, c2o, P = self.cfg, self.O, self.C, self.c2o, self.P
        sell = lv.side == "sell"
        conf_k = self.conf_index(brk, bar)
        ref = C["close"][conf_k]
        conf_o = c2o[conf_k]
        t_conf = self.c_end[conf_k]
        closed_o = int(np.searchsorted(self.o_end, t_conf, "right")) - 1  # last origin bar closed at confirmation

        if self.overlap(lv, bar, t_conf):
            rule += "+overlap"
            target = self.target(sell, closed_o, t_conf, ref, "kl")
        else:
            target = self.target(sell, closed_o, t_conf, ref, "erl" if rule == "cadjpy" else "nearest")
        if target is None:
            return None
        stop = (O["high"][bar] + cfg["stop_buffer_pips"] * P) if sell else (O["low"][bar] - cfg["stop_buffer_pips"] * P)
        risk = (stop - ref) if sell else (ref - stop)
        if risk <= 0:
            return None
        R = abs(target - ref) / risk

        # outcome A (trade): target vs stop on confirm-TF bars. Outcome B (Kevin): target vs origin close through
        # level, or the story ends early by a flip (#29)
        end_o = min(conf_o + cfg["max_hold"], len(O["close"]) - 1)
        fl = self.flip_scan(lv, target, closed_o, end_o) if cfg["flip_end"] else None
        flip_k = fl[0] if fl else None
        out, res, inv, exit_k, inv_k = "timeout", None, "open", None, None
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
                    inv, inv_k = "target", k
                elif k == self.first_k[c2o[k] + 1] - 1 and ((O["close"][c2o[k]] > lv.price) if sell else (O["close"][c2o[k]] < lv.price)):
                    inv, inv_k = "invalidated", k
            if k == flip_k:
                if inv == "open":
                    inv, inv_k = "ended_flip", k
                if out == "timeout":  # the trade is closed when the story ends
                    out, exit_k = "flip", k
                    res = ((ref - C["close"][k]) if sell else (C["close"][k] - ref)) / risk
            if out != "timeout" and inv != "open":
                break
            k += 1
        last = min(k, len(C["close"])) - 1  # last bar inside the hold window (k is the first one past it)
        if out == "timeout":
            res = ((ref - C["close"][last]) if sell else (C["close"][last] - ref)) / risk
        done_o = c2o[exit_k] if exit_k is not None else c2o[last]
        why = {"target": f"target {_r(target)} reached",
               "invalidated": f"{self.otf} close back through the origin level {_r(lv.price)}",
               "open": None}
        r = {
            "side": "SELL" if sell else "BUY", "B": B, "breakout_time": str(self.c_start[brk])[:16],
            "confirm_time": str(self.c_end[conf_k])[:16], "entry_ref": ref, "target": target, "stop": stop,
            "R": round(R, 2), "outcome": out, "result_R": round(res, 2), "kevin_outcome": inv,
            "stop_pips": round(risk / P, 1), "break_kind": kind, "rule": rule, "_busy": int(done_o),
            "retrace": None if kind == "none" else self.retrace(sell, B, brk),
        }
        if inv == "ended_flip":
            _, fo, f, fB = fl
            r["end_reason"] = (f"flip: {self.otf} {f.kind} level {_r(f.price)} rejected the other way "
                               f"({str(self.o_start[fo])[:10]}) + {self.ctf} close {'above' if sell else 'below'} "
                               f"its point B {_r(fB)}")
            r["end_time"] = str(self.c_end[inv_k])[:16]
            r["_busy"] = int(min(done_o, fo - 1))
            r["_flip"] = (fo, f)
        else:
            r["end_reason"] = why.get(inv)
            if inv_k is not None:
                r["end_time"] = str(self.c_end[inv_k])[:16]
        return r

    # ------------------------------------------------------------------ #31b alignment
    def align_starts(self):
        """#31b [T weekly-recap@151-282 ("a simple BOS on weekly and then it should happen on daily and then it should
        happen on the four hours ... when it is not like this ... no trading opportunities because these alignments
        were not there"), 626-670 ("weekly and daily breaking structure on the downside: an H4 structure up, does
        it make sense to buy? No"), 2098-2160 ("if weekly does this, wait for daily to do it, maybe not on Monday
        ... Friday"); F weekly-recap/sheet_003-008 (W close below the last weekly V 1.7172, D line-chart ladder of
        swing lows, H4 sell)]: origin bar d -> (Level 'align' at the protected D swing, point B, breakout index).
        W: the last W structural break (a W close beyond the last W swing) closed before D bar d starts.
        D: bar d closes beyond the last D swing the same way (structural_swings fix at d).
        H4: after D bar d closes, a close beyond the last H4 close turn made since d started (same day close rule),
        within max_wait D bars; a D close back through the protected D swing first cancels it."""
        cfg, O, C, c2o = self.cfg, self.O, self.C, self.c2o
        if self.hb is None:
            return {}
        w_end = self.hb["end"].to_numpy()
        wbr = _breaks(_structure(self.hb, cfg))  # [(known_at, dir, protected)]
        w_t = np.array([w_end[i] for i, _, _ in wbr]) if wbr else np.array([], dtype=w_end.dtype)
        out = {}
        for d, up, prot in _breaks(_structure(pd.DataFrame({"close": O["close"]}), cfg)):
            j = int(np.searchsorted(w_t, self.o_start[d], "right")) - 1  # last W break closed before d
            if j < 0 or wbr[j][1] != up or d + 1 >= len(self.first_k):
                continue
            k = int(self.first_k[d + 1])
            last_o = min(d + cfg["max_wait"], len(O["close"]) - 1)
            brk = B = None
            while k < len(C["close"]) and c2o[k] <= last_o:
                oi = c2o[k]
                if k == self.first_k[oi] and oi - 1 > d and \
                        ((O["close"][oi - 1] < prot) if up else (O["close"][oi - 1] > prot)):
                    break  # D close back through the protected swing: no alignment
                pts = [s for s in self.csw.at(k - 1) if s[1] == ("H" if up else "L") and s[0] >= self.first_k[d]]
                if pts and ((C["close"][k] > pts[-1][2]) if up else (C["close"][k] < pts[-1][2])):
                    ok = (O["close"][oi] > pts[-1][2]) if up else (O["close"][oi] < pts[-1][2])
                    if not cfg["same_bar_close"] or ok:
                        brk, B = k, pts[-1][2]
                        break
                    k = int(self.first_k[oi + 1])
                    continue
                k += 1
            if brk is not None:
                out[d] = (Level(prot, "buy" if up else "sell", "align", d, [(d, "tap", True)]), B, brk)
        return out


def _breaks(sw):
    """Structural breaks from structural_swings output: [(breaking bar, up?, protected swing price)]. The last
    swing fixed at a breaking bar is the opposite swing that pushed price through (L = a close above the swing
    high = up; its price is the protected HL)."""
    last = {}
    for s in sw:
        last[s[3]] = s
    return [(i, s[1] == "L", s[2]) for i, s in sorted(last.items())]


def _break_kind(sell, sw, k0, brk, C):
    """Label only (the break itself is always the external close beyond B). "sweep_break" when, between the
    first tap and the breakout, a confirm-TF wick went beyond the last swing high (sell; low for buy) made
    before the tap and the candle closed back inside: a sweep of that liquidity, then the break (advanced
    structure = sweep -> BOS) [T story-line-pt2@405-436; notes_structure §4]. Otherwise "breakout"."""
    liq = [s[0] for s in sw if s[1] == ("H" if sell else "L") and s[0] < k0]
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
    find_stories (incl. #26 most recent level, #30 targets). `h1` must end with closed bars only. Returns a dict
    (status 'TAPPED') or None. A tap that already broke out, or that the CADJPY exception confirmed at its close,
    is find_stories' job, so None is returned for it."""
    cfg = {**DEFAULT, **(cfg or {})}
    X = _Ctx(pair, h1, story, cfg)
    O, C = X.O, X.C
    last = len(O["close"]) - 1
    tol = X.tol
    for bar in sorted(X.taps, reverse=True):
        if bar < last - cfg["max_wait"]:
            break
        if bar < 2:
            continue
        tr = trend(X.osw.at(bar - 1), O["close"][bar - 1])
        lv = X.choose(bar, tr)
        if lv is None:
            continue
        h_tr = X.htf_trend(X.o_start[bar]) if X.htf else None
        if X.htf and cfg["htf_filter"] and _against(lv.side, h_tr):
            continue
        if X.cadjpy(lv, bar, h_tr):
            return None  # confirmed at the D close (CADJPY exception): a find_stories row
        sell = lv.side == "sell"
        ks = np.arange(X.first_k[bar], X.first_k[bar + 1])
        if not len(ks):
            continue
        touch = [k for k in ks if (C["high"][k] >= lv.price - tol if sell else C["low"][k] <= lv.price + tol)]
        k0 = touch[0] if touch else ks[0]
        B = _point_b(X.csw.at(k0), k0, sell)
        if B is None:
            continue
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
        tg = X.target(sell, last, X.o_end[last], min(ref, B) if sell else max(ref, B))
        return {
            "pair": pair, "story": story, "side": "SELL" if sell else "BUY", "status": "TAPPED", "trend": tr,
            "level_kind": lv.kind, "level": lv.price, "B": B, "target": tg,
            "tap_time": str(X.o_start[bar])[:16], "bars_left": int(bar + cfg["max_wait"] - last),
            "rule": "sweep_start" if lv.kind == "sweep" else "standard", "level_time": X.level_time(lv, bar),
        }
    return None
