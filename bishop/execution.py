"""Causal, conservative H1 paper execution. No broker or database calls.

Choices, not teacher rules: bid OHLC, constant declared spread, limit fills at
the requested price without favourable gap improvement, adverse opening-gap
stops, stop-first ambiguity and no intrabar fill-bar target assumption. Exact
intrabar execution requires finer data; fill times here are observation clocks.
"""
from dataclasses import dataclass
import math

import pandas as pd

from .coverage import validate_hourly, expected_hours
from .instruments import pip
from .price_action import _time


@dataclass(frozen=True)
class Costs:
    spread_pips: float
    stop_slippage_pips: float
    commission_pips: float  # entire round trip, deducted once

    def __post_init__(self):
        for name in ("spread_pips", "stop_slippage_pips", "commission_pips"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("costs must be explicit finite nonnegative pip values")


@dataclass(frozen=True)
class Order:
    id: str
    pair: str
    side: str
    tf: str
    mode: str
    entry: float
    stop: float
    target: float
    available_at: object
    expires_at: object
    bias_side: str
    bias_tf: str
    cancel_at: object = None

    def __post_init__(self):
        if self.side not in ("BUY", "SELL") or self.bias_side not in ("BUY", "SELL"):
            raise ValueError("invalid order or bias side")
        for key in ("id", "pair", "tf", "mode", "bias_tf"):
            if not isinstance(getattr(self, key), str) or not getattr(self, key):
                raise ValueError(f"missing {key}")
        for key in ("entry", "stop", "target"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"invalid {key}")
        correct = self.stop < self.entry < self.target if self.side == "BUY" else self.target < self.entry < self.stop
        if not correct:
            raise ValueError("invalid order price geometry")
        available, expiry = _time(self.available_at, "available_at"), _time(self.expires_at, "expires_at")
        if expiry <= available:
            raise ValueError("expiry must follow setup availability")
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "expires_at", expiry)
        if self.cancel_at is not None:
            cancelled = _time(self.cancel_at, "cancel_at")
            if cancelled <= available:
                raise ValueError("cancellation must follow setup availability")
            object.__setattr__(self, "cancel_at", cancelled)


def simulate(order, h1, *, as_of, costs):
    """Return one observation, never infer an unseen fill from a later bar.

    Only a full hourly bar starting at/after setup availability may fill.
    Missing active market hours censor the path. A partial expiry bar is not
    used to infer either a fill or a miss. Once filled, exits remain active
    after the pending-order expiry (there is no invented holding-period exit).
    """
    if not isinstance(order, Order) or not isinstance(costs, Costs):
        raise ValueError("an Order and explicit Costs are required")
    clock = _time(as_of, "as_of")
    # Reject future candles rather than consume them and trim their results.
    bars = validate_hourly(h1, as_of=clock)
    return _simulate(order, bars, clock, costs)


def simulate_many(orders, h1, *, as_of, costs):
    """Validate the frozen feed once; preserve single-order execution results."""
    orders = tuple(orders)
    if not isinstance(costs, Costs) or any(not isinstance(o, Order) for o in orders):
        raise ValueError("Orders and explicit Costs required")
    clock = _time(as_of, "as_of")
    bars = validate_hourly(h1, as_of=clock)
    earliest = min((o.available_at.floor("h") for o in orders), default=clock.floor("h"))
    hours = expected_hours(min(earliest, clock.floor("h")), clock.floor("h"))
    return [_simulate(o, bars, clock, costs, hours) for o in orders]


def _simulate(order, bars, clock, costs, hours=None):
    result = {"id": order.id, "pair": order.pair, "side": order.side, "tf": order.tf,
              "mode": order.mode, "entry": order.entry, "requested_entry": order.entry,
              "stop": order.stop, "target": order.target,
              "bias": {"side": order.bias_side, "tf": order.bias_tf},
              "setup_time": order.available_at.isoformat(), "status": "PENDING", "outcome": "OPEN",
              "observed_at": clock.isoformat(),
              "pending_end": None,
              "time": None, "fill_price": None, "fill_window": None,
              "exit_time": None, "exit_price": None, "net_r": None,
              "execution_resolution": "H1; time is first-observed fill-bar end, not exact intrabar fill",
              "costs": vars(costs), "flags": []}
    if clock < order.available_at:
        result.update(status="UNAVAILABLE", outcome="UNAVAILABLE")
        return result
    if order.available_at != order.available_at.floor("h"):
        result.update(status="CENSORED", outcome="CENSORED")
        result["flags"].append("setup became available inside H1; initial active path is unresolved")
        return result
    start = order.available_at.ceil("h")
    horizon = clock.floor("h")
    if horizon < start:
        return result
    spread, slip = costs.spread_pips * pip(order.pair), costs.stop_slippage_pips * pip(order.pair)
    risk = abs(order.entry - order.stop)
    # Iterate expected hours so a gap is encountered BEFORE any subsequent fill.
    filled = False
    active_hours = expected_hours(start, horizon) if hours is None else hours[hours.searchsorted(start):]
    for at in active_hours:
        end = at + pd.Timedelta(hours=1)
        if not filled and order.cancel_at is not None and order.cancel_at <= order.expires_at and at >= order.cancel_at:
            result.update(status="CANCELLED", outcome="STORY_ENDED", pending_end=order.cancel_at.isoformat())
            break
        if not filled and at >= order.expires_at:
            result.update(status="MISSED", outcome="EXPIRED", pending_end=order.expires_at.isoformat())
            break
        if at not in bars.index:
            result.update(outcome="CENSORED")
            if not filled:
                result["status"] = "CENSORED"
            result["flags"].append(f"missing market hour {at.isoformat()}")
            break
        if not filled and end > order.expires_at:
            result.update(status="CENSORED", outcome="CENSORED")
            result["flags"].append("pending expiry inside an H1 candle")
            break
        if not filled and order.cancel_at is not None and end > order.cancel_at:
            result.update(status="CENSORED", outcome="CENSORED")
            result["flags"].append("story cancellation inside an H1 candle")
            break
        row = bars.loc[at]
        just_filled = False
        if not filled:
            touched = row.low + spread <= order.entry if order.side == "BUY" else row.high >= order.entry
            if not touched:
                continue
            filled, just_filled = True, True
            result.update(status="FILLED", time=end.isoformat(), fill_price=order.entry, pending_end=end.isoformat(),
                          fill_window={"start": at.isoformat(), "end": end.isoformat()})
            marketable = row.open + spread < order.entry if order.side == "BUY" else row.open > order.entry
            if marketable:
                result["flags"].append("marketable at bar open; conservative requested-price fill without improvement")
        if order.side == "BUY":
            stopped, target = row.low <= order.stop, row.high >= order.target
            stop_fill = min(order.stop, row.open) - slip
        else:
            stopped, target = row.high + spread >= order.stop, row.low + spread <= order.target
            stop_fill = max(order.stop, row.open + spread) + slip
        if stopped:
            if target:
                result["flags"].append("stop and target inside same H1 bar; stop-first assumption")
            exit_price, outcome = stop_fill, "LOSS"
        elif target and just_filled:
            result.update(outcome="CENSORED")
            result["flags"].append("fill-bar target sequence is not established")
            break
        elif target:
            exit_price, outcome = order.target, "WIN"
        else:
            continue
        signed = (exit_price - order.entry) * (1 if order.side == "BUY" else -1)
        result.update(outcome=outcome, exit_price=exit_price, exit_time=end.isoformat(),
                      net_r=(signed - costs.commission_pips * pip(order.pair)) / risk)
        break
    else:
        if not filled and order.cancel_at is not None and clock >= order.cancel_at and order.cancel_at <= order.expires_at:
            if order.cancel_at != order.cancel_at.floor("h"):
                result.update(status="CENSORED", outcome="CENSORED")
                result["flags"].append("story cancellation timing is finer than H1")
            else:
                result.update(status="CANCELLED", outcome="STORY_ENDED", pending_end=order.cancel_at.isoformat())
        elif not filled and clock >= order.expires_at:
            if order.expires_at != order.expires_at.floor("h"):
                result.update(status="CENSORED", outcome="CENSORED")
                result["flags"].append("expiry timing is finer than H1")
            else:
                result.update(status="MISSED", outcome="EXPIRED", pending_end=order.expires_at.isoformat())
    return result
