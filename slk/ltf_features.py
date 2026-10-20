"""Lower-TF context of one entry, measured ONLY from candles closed at the entry time (no look-ahead).
Used by slk/trend_study.py (one row per trade) and slk/ltf_discovery.py (which features help?). Owner 2026-10-20:
"in every entry ... go to lower time frames and check, is there any significant something ... that gives a
higher probability of this trade actually going in our direction and even a higher fixed reward".

Feature ideas from Kevin's teaching (research/TREND_LTF_PLAN.md); every one is a measurement, none is a rule yet.
H1 = dict of numpy arrays t (UTC naive datetime64, candle OPEN time), open, high, low, close. k = index of the
H1 candle whose close is the entry (the confirmation candle). All windows end at k.

  stop_pips          risk in pips (entry close -> stop)
  atr_pips           H1 ATR(14) in pips at k
  stop_atr           risk / ATR
  break_body_atr     body of the confirmation candle / ATR (impulsive break = large)
  break_close_pos    where the close sits in that candle's range, 1 = at the extreme in the trade direction
  fvg                the break left an imbalance: candle k-2 and candle k do not overlap (sell: low[k-2] > high[k])
  fvg_pips           size of that gap (0 if none)
  sweep              the tap swept liquidity: the extreme from the tap to k went beyond the extreme of the
                     24 H1 candles before the tap (sell: a higher high), then price came back
  h1_trend_agrees    H1 close-line structure (order-1 pivots) trends the trade way at k
  run_R              how far the entry already is from the tap extreme, in R (late entry = big)
  hours_tap_to_entry hours from the H4 tap candle open to the entry close
  hour_utc           hour of the entry close (UTC); session = asia 0-7 / london 7-12 / ny 12-17 / late 17-24
  prev_day_pos       entry inside the previous D range: 0 = at its low, 1 = at its high (sell wants high = premium)
  dow                weekday of the entry close (0 = Monday)
"""
import numpy as np

from .structure import SwingBook, pivots, structural_swings, trend

LOOKBACK = 24   # H1 candles before the tap for the sweep test
ATR_N = 14


def atr(H, k, n=ATR_N):
    lo = max(1, k - n + 1)
    hi, lw, pc = H["high"][lo:k + 1], H["low"][lo:k + 1], H["close"][lo - 1:k]
    tr = np.maximum(hi - lw, np.maximum(abs(hi - pc), abs(lw - pc)))
    return float(tr.mean()) if len(tr) else float(H["high"][k] - H["low"][k])


def session(hour):
    return "asia" if hour < 7 else "london" if hour < 12 else "ny" if hour < 17 else "late"


class H1Trend:
    """H1 structure trend at any index without look-ahead (pivots are known only n candles after they form)."""

    def __init__(self, H):
        c = np.asarray(H["close"], float)
        self.c, self.sb = c, SwingBook(structural_swings(c, pivots(c, 1)))

    def at(self, k):
        return trend(self.sb.at(k), float(self.c[k]))


def features(H, k, side, entry, stop, tap_start, pip, h1trend=None, prev_day=None):
    """tap_start = index of the first H1 candle of the H4 tap candle. prev_day = (high, low) of the last D candle
    closed before the entry, or None."""
    sell = side == "SELL"
    risk = abs(stop - entry)
    a = atr(H, k)
    o, h, l, c = H["open"][k], H["high"][k], H["low"][k], H["close"][k]
    rng = h - l
    body = abs(c - o)
    pos = ((h - c) / rng if sell else (c - l) / rng) if rng > 0 else 0.5
    gap = (H["low"][k - 2] - h) if sell else (l - H["high"][k - 2]) if k >= 2 else 0.0
    gap = max(0.0, float(gap)) if k >= 2 else 0.0
    b0 = max(0, tap_start - LOOKBACK)
    if tap_start > b0:
        before = H["high"][b0:tap_start].max() if sell else H["low"][b0:tap_start].min()
        ext = H["high"][tap_start:k + 1].max() if sell else H["low"][tap_start:k + 1].min()
        sweep = bool(ext > before) if sell else bool(ext < before)
    else:
        ext, sweep = (H["high"][k] if sell else H["low"][k]), False
    run = ((ext - entry) if sell else (entry - ext)) / risk if risk > 0 else np.nan
    ht = (h1trend.at(k) if h1trend else None)
    t_close = H["t"][k] + np.timedelta64(1, "h")
    hour = int((t_close.astype("datetime64[h]").astype(int)) % 24)
    dow = int(((t_close.astype("datetime64[D]").astype(int)) + 3) % 7)  # 1970-01-01 was a Thursday
    pdp = None
    if prev_day and prev_day[0] > prev_day[1]:
        pdp = (entry - prev_day[1]) / (prev_day[0] - prev_day[1])
    return {"stop_pips": round(risk / pip, 1), "atr_pips": round(a / pip, 1),
            "stop_atr": round(risk / a, 2) if a > 0 else np.nan,
            "break_body_atr": round(body / a, 2) if a > 0 else np.nan, "break_close_pos": round(float(pos), 2),
            "fvg": gap > 0, "fvg_pips": round(gap / pip, 1), "sweep": sweep,
            "h1_trend_agrees": ht == ("down" if sell else "up") if ht else None,
            "run_R": round(float(run), 2), "hours_tap_to_entry": int(k + 1 - tap_start),
            "hour_utc": hour, "session": session(hour),
            "prev_day_pos": round(float(pdp), 2) if pdp is not None else None, "dow": dow}
