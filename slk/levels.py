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
            lv.append(Level(c[i], "sell", "A", known))
        elif p[1] == "L" and bear[i] and bull[j]:
            lv.append(Level(c[i], "buy", "V", known))
        if cfg["use_oc"] and j + 1 < len(c):
            # open-close: first two same-colour candles that start the leg away from the swing
            k = j + 1
            if p[1] == "H" and bear[j] and bear[k]:
                lv.append(Level(c[j], "sell", "OC", max(k, p[3]) + 1))
            elif p[1] == "L" and bull[j] and bull[k]:
                lv.append(Level(c[j], "buy", "OC", max(k, p[3]) + 1))
    return lv


def run_levels(bars, levels, tol):
    """Walk each level forward. First wick touch = the tap (level used); a body close through = break,
    which creates a fresh flipped level on the other side (STRATEGY §1). Returns all levels incl. flips."""
    h, l, c = bars["high"].to_numpy(), bars["low"].to_numpy(), bars["close"].to_numpy()
    out, queue = [], list(levels)
    while queue:
        lv = queue.pop()
        out.append(lv)
        used = False
        for b in range(lv.born, len(c)):
            if lv.side == "sell":
                broke, touched = c[b] > lv.price, h[b] >= lv.price - tol
            else:
                broke, touched = c[b] < lv.price, l[b] <= lv.price + tol
            if broke:  # a used level also becomes fresh again (flipped) after a body close through
                lv.events.append((b, "break", False))
                queue.append(Level(lv.price, "buy" if lv.side == "sell" else "sell", "flip", b + 1))
                break
            if touched and not used:
                lv.events.append((b, "tap", True))  # close stayed on the original side = rejection
                used = True  # Kevin uses a level once
    return out
