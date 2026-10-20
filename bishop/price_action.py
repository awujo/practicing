"""Closed-candle key-level primitives, not a completed Bishop trading engine.

Sources: core video-11@60-111,151-270 (A/V/OC and role changes),
video-3@427-535 (wick excursion versus body closure).

Explicit conservative choices:
* A/V use TWO opposite-direction candles, not an extra confirmation candle.
  The body junction is candle one's close, exactly equal to candle two's open.
  On continuous candles this is the familiar close-line turn. Gapped junctions
  are skipped: no inferred tolerance or level interpolation is a teacher rule.
* Same-direction candles with that exact junction form OC; dojis form no level.
  Explicit alternate ``close_reference`` mode uses the first close without
  requiring the next open to equal it, and requires the second close to finish
  on its proposed side. It does not interpolate gaps or introduce a tolerance.
* A level becomes available at candle TWO's end. It cannot classify its own
  formation candle. A level break here is not an inferred structural BOS or
  an 'impulsive' trade trigger: no numerical impulse threshold is invented.

Input timestamps are candle ENDS, either in an explicit ``end`` column or an
aware DatetimeIndex. A raw candle-start-indexed feed must be converted first.
``as_of`` is an explicit historical clock (defaults to current UTC); future or
forming bars are rejected, not silently treated as closed.
"""
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


def _time(value, name):
    try:
        t = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a timezone-aware timestamp") from exc
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError(f"{name} must be a timezone-aware timestamp")
    return t.tz_convert("UTC")


def _clock(as_of):
    return pd.Timestamp.now(tz="UTC") if as_of is None else _time(as_of, "as_of")


@dataclass(frozen=True)
class KeyLevel:
    kind: Literal["A", "V", "OC"]
    price: float
    side: Literal["BUY", "SELL"]
    formed_at: pd.Timestamp
    available_at: pd.Timestamp

    def __post_init__(self):
        if self.kind not in ("A", "V", "OC") or self.side not in ("BUY", "SELL"):
            raise ValueError("invalid level kind or side")
        try:
            price = float(self.price)
        except (TypeError, ValueError) as exc:
            raise ValueError("level price must be finite") from exc
        if not np.isfinite(price):
            raise ValueError("level price must be finite")
        formed = _time(self.formed_at, "formed_at")
        available = _time(self.available_at, "available_at")
        if available < formed:
            raise ValueError("level cannot be available before formation")
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "formed_at", formed)
        object.__setattr__(self, "available_at", available)


@dataclass(frozen=True)
class PriceEvent:
    kind: Literal["TOUCH", "SWEEP", "BREAK"]
    side: Literal["BUY", "SELL"]
    occurred_at: pd.Timestamp
    available_at: pd.Timestamp


def validated_bars(bars, *, as_of=None):
    """Return a copied float OHLC frame indexed by verified UTC candle ends.

    An explicit ``end`` column takes precedence over the index; this accepts
    ``bishop.candles.completed`` output without confusing observed starts with
    nominal ends. No sorting, deduplication, price repair or future filtering.
    """
    if not isinstance(bars, pd.DataFrame):
        raise ValueError("bars must be a pandas DataFrame")
    required = ["open", "high", "low", "close"]
    if bars.columns.has_duplicates or not set(required).issubset(bars.columns):
        raise ValueError("bars need unique open/high/low/close columns")
    if "end" in bars.columns:
        times = [_time(v, "bar end") for v in bars["end"]]
    elif isinstance(bars.index, pd.DatetimeIndex):
        if bars.index.tz is None:
            raise ValueError("bar ends must include a timezone")
        times = [_time(v, "bar end") for v in bars.index]
    else:
        raise ValueError("bars need an end column or aware DatetimeIndex of ends")
    idx = pd.DatetimeIndex(times, tz="UTC", name="end")
    if not idx.is_monotonic_increasing or idx.has_duplicates:
        raise ValueError("bar ends must be strictly increasing and unique")
    if len(idx) and idx[-1] > _clock(as_of):
        raise ValueError("future/forming candle end exceeds as_of")
    # Validate the clock even for an empty frame.
    if not len(idx):
        _clock(as_of)
    try:
        values = bars[required].to_numpy(dtype=float, copy=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("OHLC values must be finite numbers") from exc
    if not np.isfinite(values).all():
        raise ValueError("OHLC values must be finite numbers")
    if len(values):
        o, h, lo, c = values.T
        if ((lo > np.minimum(o, c)) | (h < np.maximum(o, c)) | (lo > h)).any():
            raise ValueError("invalid OHLC bounds")
    return pd.DataFrame(values, index=idx, columns=required)


def levels(bars, *, as_of=None, level_mode="exact_junction"):
    """Find causal two-candle A/V/OC levels in oldest-availability order.

    ``formed_at`` is the first candle's junction close; ``available_at`` is
    the second candle's completed end. Returned levels are candidates, not
    confirmed bias, fresh-level assertions or trading recommendations.
    The default preserves exact junctions. ``close_reference`` is an explicit
    alternate interpretation of S01, not an automatically selected relaxation.
    """
    if level_mode not in ("exact_junction", "close_reference"):
        raise ValueError("level_mode must be exact_junction or close_reference")
    frame = validated_bars(bars, as_of=as_of)
    out = []
    for i in range(1, len(frame)):
        left, right = frame.iloc[i - 1], frame.iloc[i]
        if level_mode == "exact_junction" and left["close"] != right["open"]:
            continue  # Explicit exact-junction policy; no inferred gap level.
        a = np.sign(left["close"] - left["open"])
        b = np.sign(right["close"] - right["open"])
        if not a or not b:
            continue
        # Source S01 places the thin line at the first closing price. This
        # alternate policy does not average the gap or fit a pip tolerance.
        # Require candle two to finish on its proposed side of that reference.
        if level_mode == "close_reference" and np.sign(right["close"] - left["close"]) != b:
            continue
        kind = "OC" if a == b else ("A" if a > 0 else "V")
        out.append(KeyLevel(kind, left["close"], "BUY" if b > 0 else "SELL",
                            frame.index[i - 1], frame.index[i]))
    return out


def classify(level, bar, *, as_of=None):
    """Classify one completed candle against a level's current role.

    ``bar`` is a Series with OHLC and an aware end timestamp in ``end`` or
    its name. BUY support: close below is BREAK/SELL; strict low excursion
    below with close back at/above is SWEEP/BUY. SELL resistance mirrors it.
    An exact wick touch is TOUCH. No contact, or a candle ending before/at
    level availability, returns None. This function does not mutate or flip
    a level, infer freshness, enforce impulse or claim a structural BOS.
    """
    if not isinstance(level, KeyLevel):
        raise ValueError("level must be a KeyLevel")
    if not isinstance(bar, pd.Series):
        raise ValueError("bar must be a pandas Series with an end timestamp")
    row = bar.copy()
    if "end" not in row.index:
        row["end"] = bar.name
    frame = validated_bars(pd.DataFrame([row]), as_of=as_of)
    at = frame.index[0]
    if at <= level.available_at:
        return None
    candle = frame.iloc[0]
    p, close = level.price, candle["close"]
    if level.side == "BUY":
        kind = "BREAK" if close < p else ("SWEEP" if candle["low"] < p else None)
        side = "SELL" if kind == "BREAK" else "BUY"
    else:
        kind = "BREAK" if close > p else ("SWEEP" if candle["high"] > p else None)
        side = "BUY" if kind == "BREAK" else "SELL"
    if kind is None and candle["low"] <= p <= candle["high"]:
        kind = "TOUCH"
    return PriceEvent(kind, side, at, at) if kind is not None else None
