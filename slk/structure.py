"""Market structure on the LINE chart (closes only). STRATEGY §1."""
import numpy as np


def pivots(close, n):
    """Close-line turning points: list of (idx, kind 'H'/'L', price, known_at_idx).

    A pivot at i is a close that is the extreme of closes i-n..i+n; it is only known
    at bar i+n (no look-ahead).
    """
    c = np.asarray(close, dtype=float)
    if n < 1:  # degenerate order: original bar-by-bar rule (c[i - 1] wraps at i = 0)
        out = []
        for i in range(n, len(c) - n):
            w = c[i - n:i + n + 1]
            if c[i] == w.max() and c[i] > c[i - 1]:
                out.append((i, "H", c[i], i + n))
            elif c[i] == w.min() and c[i] < c[i - 1]:
                out.append((i, "L", c[i], i + n))
        return out
    if len(c) < 2 * n + 1:
        return []
    w = np.lib.stride_tricks.sliding_window_view(c, 2 * n + 1)  # window of bar i = row i - n
    mid, prev = c[n:len(c) - n], c[n - 1:len(c) - n - 1]
    hi = (mid == w.max(axis=1)) & (mid > prev)
    lo = ~hi & (mid == w.min(axis=1)) & (mid < prev)
    return [(int(i), "H" if hi[i - n] else "L", c[i], int(i) + n) for i in np.flatnonzero(hi | lo) + n]


def structural_swings(close, piv):
    """Kevin's swings for TREND and targets (STRATEGY §1, REVIEW #23): only the main legs of the close line.

    A swing is fixed only when a later close goes beyond the previous opposite swing [T basic-ms@456-620,
    F basic-ms/sheet_004]: a close above the last swing high fixes the swing low = the lowest close between that
    high and the breaking close ("the lowest point that pushed price to take out the high"; a deeper dip before
    the break replaces an earlier candidate); a close below the last swing low fixes the swing high = the highest
    close in between (mirror; a break against the trend = BMS). The high/low that has to be broken is the most
    extreme close-line turning point (`piv`, already known) after the last fix, so wiggles inside a pullback
    (a lower high in an uptrend, a higher low in a downtrend) never become swings.

    Returns (idx, 'H'/'L', price, known_at) like `pivots`, strictly alternating; known_at = the breaking bar
    (no look-ahead), non-decreasing, so SwingBook/swings() work on it unchanged."""
    c = np.asarray(close, dtype=float)
    out = []
    ref = {"H": None, "L": None}  # (idx, price) a close must go beyond; the protected one is never moved
    pend = {"H", "L"}             # refs still being searched: the most extreme turning point since the last fix
    since, j = 0, 0
    for i in range(len(c)):
        while j < len(piv) and piv[j][3] <= i:  # turning points known by bar i
            p = piv[j]
            j += 1
            k = p[1]
            if k in pend and p[0] >= since and (ref[k] is None or (p[2] > ref[k][1] if k == "H" else p[2] < ref[k][1])):
                ref[k] = (p[0], p[2])
        for k, beyond in (("H", lambda x, r: x > r), ("L", lambda x, r: x < r)):
            r = ref[k]
            if r is None or not beyond(c[i], r[1]) or i < r[0] + 2:
                continue
            if not out or out[-1][1] != k:
                out.append((r[0], k, r[1], i))        # the broken extreme is a swing (unless already the last one)
            seg = c[r[0] + 1:i]
            m = r[0] + 1 + int(seg.argmin() if k == "H" else seg.argmax())
            o = "L" if k == "H" else "H"
            out.append((m, o, c[m], i))                # the opposite swing that pushed price through it
            ref[o], ref[k], pend, since = (m, c[m]), None, {k}, i
            break
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


class SwingBook:
    """`swings(piv, upto)` for many `upto` values without rebuilding the list each time (same output).

    Pivots become known in index order (known_at = idx + n is increasing), so swings(piv, upto) only depends on
    how many pivots are known; each state is a linked node (last swing, previous state)."""

    def __init__(self, piv):
        from bisect import bisect_right
        self._bisect = bisect_right
        self.keys = [p[3] for p in piv]
        cur, self._states = None, [None]
        for p in piv:
            if cur is not None and cur[0][1] == p[1]:
                if (p[1] == "H" and p[2] >= cur[0][2]) or (p[1] == "L" and p[2] <= cur[0][2]):
                    cur = (p, cur[1])
            else:
                cur = (p, cur)
            self._states.append(cur)
        self._memo = {}

    def at(self, upto):
        """Same list as swings(piv, upto). Treat it as read-only (it is shared between calls)."""
        k = self._bisect(self.keys, upto)
        sw = self._memo.get(k)
        if sw is None:
            sw, node = [], self._states[k]
            while node is not None:
                sw.append(node[0])
                node = node[1]
            sw.reverse()
            self._memo[k] = sw
        return sw
