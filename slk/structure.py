"""Market structure on the LINE chart (closes only). STRATEGY §1."""
import numpy as np


def pivots(close, n):
    """Close-line turning points: list of (idx, kind 'H'/'L', price, known_at_idx).

    A pivot at i is a close that is the extreme of closes i-n..i+n; it is only known
    at bar i+n (no look-ahead).
    """
    c = np.asarray(close, dtype=float)
    out = []
    for i in range(n, len(c) - n):
        w = c[i - n:i + n + 1]
        if c[i] == w.max() and c[i] > c[i - 1]:
            out.append((i, "H", c[i], i + n))
        elif c[i] == w.min() and c[i] < c[i - 1]:
            out.append((i, "L", c[i], i + n))
    return out


def swings(piv, upto):
    """Alternating swing list from pivots known at bar `upto` (keep the more extreme of repeats)."""
    sw = []
    for p in piv:
        if p[3] > upto:
            break
        if sw and sw[-1][1] == p[1]:
            if (p[1] == "H" and p[2] >= sw[-1][2]) or (p[1] == "L" and p[2] <= sw[-1][2]):
                sw[-1] = p
            continue
        sw.append(p)
    return sw


def trend(sw, last_close):
    """'up' (HH+HL), 'down' (LH+LL) or 'range'. A close beyond the last opposite swing flips it (BMS)."""
    hs = [s[2] for s in sw if s[1] == "H"][-2:]
    ls = [s[2] for s in sw if s[1] == "L"][-2:]
    if len(hs) < 2 or len(ls) < 2:
        return "range"
    t = "up" if hs[1] > hs[0] and ls[1] > ls[0] else "down" if hs[1] < hs[0] and ls[1] < ls[0] else "range"
    if t == "up" and last_close < ls[1]:
        return "down"
    if t == "down" and last_close > hs[1]:
        return "up"
    if t == "range":  # body close outside the range = breakout direction
        if last_close > hs[1]:
            return "up"
        if last_close < ls[1]:
            return "down"
    return t
