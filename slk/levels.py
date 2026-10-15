"""Key levels (A-shape, V-shape, Open-Close) and their life: fresh -> tapped / broken -> flipped. STRATEGY §1."""
from dataclasses import dataclass, field

import numpy as np

from .structure import pivots


@dataclass
class Level:
    price: float
    side: str          # 'sell' (price expected to come up into it) or 'buy'
    kind: str          # 'A', 'V', 'OC', or 'flip'
    born: int          # first bar index where the level exists (can be tapped from born on)
    events: list = field(default_factory=list)  # (bar, 'tap'|'break', rejected:bool)
    src: str = ""      # shape that drew the line: 'A', 'V' or 'OC' (a flip keeps its original level's shape)
    bar: int = -1      # the candle whose close draws the line (a flip keeps its original level's candle)
    gen: int = 0       # 0 = drawn A/V/OC level, 1 = flipped once, 2 = flip of a flip ...


def find_levels(bars, cfg):
    """All A/V/OC levels on these bars, sitting at close-line swings of order cfg['level_pivot']."""
    o, c = bars["open"].to_numpy(), bars["close"].to_numpy()
    bull, bear = c > o, c < o
    piv = {p[0]: p for p in pivots(c, cfg["level_pivot"])}
    lv = []
    for i, p in piv.items():
        j = i + 1
        if j >= len(c):
            continue
        known = max(j, p[3]) + 1
        if p[1] == "H" and bull[i] and bear[j]:
            lv.append(Level(c[i], "sell", "A", known, src="A", bar=i))
        elif p[1] == "L" and bear[i] and bull[j]:
            lv.append(Level(c[i], "buy", "V", known, src="V", bar=i))
        if cfg["use_oc"] and j + 1 < len(c):
            # open-close: first two same-colour candles that start the leg away from the swing
            k = j + 1
            if p[1] == "H" and bear[j] and bear[k]:
                lv.append(Level(c[j], "sell", "OC", max(k, p[3]) + 1, src="OC", bar=j))
            elif p[1] == "L" and bull[j] and bull[k]:
                lv.append(Level(c[j], "buy", "OC", max(k, p[3]) + 1, src="OC", bar=j))
    return lv


def touch_tol(cfg, pip):
    """Price distance within which a WICK touches a line: tap_tol_pips + level_tol_pips (broker tolerance, absorbs
    the 1-2 pip difference between IC Markets, FOREX.com and OANDA feeds; default 0 = unchanged). Used for every
    wick test (tap, fresh/untouched check, first touch, re-taps). Never used for closes: a body close through a
    level or beyond point B must be a real close beyond the price."""
    return (cfg.get("tap_tol_pips", 0.0) + cfg.get("level_tol_pips", 0.0)) * pip


def run_levels(bars, levels, tol, max_flips=None, flip_max_age=None):
    """Walk each level forward. First wick touch (within `tol`, see touch_tol) = the tap (level used); a body close
    through (exact, no tolerance) = break, which creates a fresh flipped level on the other side (STRATEGY §1).
    Returns all levels incl. flips. max_flips: how many times one drawn level may flip (None = no limit, v0.7;
    1 = only the drawn A/V/OC level flips, a broken flip is spent). flip_max_age: a break more than this many bars
    after the candle that drew the line makes no flip (None = no limit).
    (Vectorised per level; same events and order as the bar-by-bar walk: the tap is the first touch before the
    first break bar, the break bar itself never counts as a tap.)"""
    h, l, c = bars["high"].to_numpy(), bars["low"].to_numpy(), bars["close"].to_numpy()
    out, queue = [], list(levels)
    while queue:
        lv = queue.pop()
        out.append(lv)
        b0 = lv.born
        if b0 >= len(c):
            continue
        if lv.side == "sell":
            broke, touched = c[b0:] > lv.price, h[b0:] >= lv.price - tol
        else:
            broke, touched = c[b0:] < lv.price, l[b0:] <= lv.price + tol
        nb = int(broke.argmax()) if broke.any() else len(broke)
        t = touched[:nb]
        if t.any():
            lv.events.append((b0 + int(t.argmax()), "tap", True))  # close stayed on the original side = rejection
        if nb < len(broke):  # a used level also becomes fresh again (flipped) after a body close through
            lv.events.append((b0 + nb, "break", False))
            if (max_flips is None or lv.gen < max_flips) and \
                    (flip_max_age is None or lv.bar < 0 or b0 + nb - lv.bar <= flip_max_age):
                queue.append(Level(lv.price, "buy" if lv.side == "sell" else "sell", "flip", b0 + nb + 1,
                                   src=lv.src, bar=lv.bar, gen=lv.gen + 1))
    return out


def sweep_taps(bars):
    """Alternative story start without a key level [T story-line-pt3@1887-2010, pt4@1349-1500; F story-line-pt3
    sheet_026-029]: an origin candle's WICK goes beyond the previous candle's high (low) and the candle CLOSES
    back below (above) it. Returned as already-tapped pseudo levels (kind 'sweep', price = the swept previous
    high/low, born = tap = the sweep candle), so the rest of the story is the normal one: point B = the last
    lower-TF swing made before the sweep (the sweep candle's own swing does not count), body close beyond B,
    invalidation = a body close back beyond the swept high/low."""
    h, l, c = bars["high"].to_numpy(), bars["low"].to_numpy(), bars["close"].to_numpy()
    out = []
    for j in range(1, len(c)):
        if h[j] > h[j - 1] and c[j] < h[j - 1]:
            out.append(Level(h[j - 1], "sell", "sweep", j, [(j, "tap", True)]))
        if l[j] < l[j - 1] and c[j] > l[j - 1]:
            out.append(Level(l[j - 1], "buy", "sweep", j, [(j, "tap", True)]))
    return out
