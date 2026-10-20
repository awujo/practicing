"""Offline causal engine assembly for the explicitly supported first routes.

Not a live bot or a claim of teacher-example acceptance. This uses origin-KL
destinations, local close-turn confirmations and two entry models. Policy
choices and unsupported routes are returned with every run, not hidden.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform

import pandas as pd

from . import bias, candles
from .coverage import coverage, validate_hourly, expected_hours, completed_from_complete_history
from .execution import Costs, Order, simulate_many
from .instruments import pip
from .price_action import _time
from .setups import Context, RiskProfile, detect_setups, SUPPORTED_MODELS
from .universe import PAIRS

_MODULES = ("engine.py", "bias.py", "structure.py", "setups.py", "execution.py", "coverage.py", "price_action.py", "candles.py", "instruments.py")
ENGINE_SHA256 = hashlib.sha256(b"".join(name.encode() + b"\0" + Path(__file__).with_name(name).read_bytes() for name in _MODULES)).hexdigest()


def _json(value):
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _context_end(story, h1, origin, stories):
    """Conservative operating retirement, not a claim of structural bias flip."""
    possible = []
    after = h1[h1.index >= story.available_at]
    hits = after.high >= story.target if story.side == "BUY" else after.low <= story.target
    if hits.any():
        possible.append(after.index[hits][0] + pd.Timedelta(hours=1))
    later = origin[origin.end > story.available_at]
    invalid = later.close < story.level if story.side == "BUY" else later.close > story.level
    if invalid.any():
        possible.append(later.loc[invalid, "end"].iloc[0])
    possible.extend(s.available_at for s in stories if s.available_at > story.available_at and s.side != story.side)
    return min(possible) if possible else None


def run(h1, *, pair, as_of, history_start, scan_start, origin_tf, entry_tf,
        level_mode, stop_profile, costs, pending_hours, buffer_pips=0.5, fixed_stop_pips=11.0):
    """Assemble real OHLC-derived stories/setups and paper observations.

    ``history_start`` freezes warmup coverage; ``scan_start`` filters observable
    setups only after computing that warmup. Neither is inferred from outcomes.
    Missing input hours stop execution and return INCOMPLETE_DATA.
    """
    if pair not in PAIRS:
        raise ValueError("this FX-session engine currently supports the declared 28 FX pairs only")
    if origin_tf not in bias.LADDERS or entry_tf not in ("H1", "H2", "H4"):
        raise ValueError("unsupported origin or entry timeframe")
    if origin_tf == "H4" and entry_tf != "H1":
        raise ValueError("H4-origin confirmation currently supports only H1 entry patterns")
    if level_mode not in ("exact_junction", "close_reference"):
        raise ValueError("explicit level_mode required")
    if isinstance(pending_hours, bool) or not isinstance(pending_hours, int) or pending_hours <= 0:
        raise ValueError("pending_hours must be an explicit positive integer")
    if not isinstance(costs, Costs):
        raise ValueError("explicit Costs required")
    clock, first, scan = (_time(v, n) for v, n in ((as_of, "as_of"), (history_start, "history_start"), (scan_start, "scan_start")))
    if not first <= scan <= clock:
        raise ValueError("history_start <= scan_start <= as_of required")
    # Validate even extra historical rows before taking the fixed warmup window.
    source = validate_hourly(h1, as_of=clock)
    source = source[source.index >= first]
    if len(source.index.difference(expected_hours(first, clock.floor("h")))):
        raise ValueError("input includes candles outside the declared FX session calendar")
    check = coverage(source, first, clock.floor("h"))
    result = {"status": "INCOMPLETE_DATA", "pair": pair, "as_of": clock.isoformat(),
              "engine_sha256": ENGINE_SHA256, "runtime": {"python": platform.python_version(), "pandas": pd.__version__},
              "history_start": first.isoformat(), "scan_start": scan.isoformat(), "coverage": check,
              "policies": {"level_mode": level_mode, "structure": "latest_close_turn",
                           "target": "nearest_known_unbroken_opposing_ORIGIN_KL_not_ERL",
                           "context_retirement": "target_or_origin_close_invalidation_or_opposite_confirmation",
                           "stop_profile": stop_profile, "buffer_pips": buffer_pips,
                           "fixed_stop_pips": fixed_stop_pips, "pending_hours": pending_hours,
                           "models": list(SUPPORTED_MODELS), "candidate_selection": "unranked alternatives; not a portfolio or mandated stacking",
                           "same_clock_opposite_contexts": "skip conflicting contexts; do not guess a side",
                           "costs": asdict(costs)},
              "unsupported_routes": list(bias.UNSUPPORTED_ROUTES) + ["nearest_ERL_target_selection", "direct_h4", "direct_h2", "engulf_irl_retest", "aggressive_fvg_direct", "M30_H3_entries", "broker_execution"],
              "stories": [], "setups": [], "observations": [], "skipped": []}
    if check["status"] != "COMPLETE":
        return result
    confirmation_tf = bias.LADDERS[origin_tf]
    prepared = [completed_from_complete_history(source, tf, as_of=clock) for tf in (origin_tf, confirmation_tf, entry_tf)]
    origin, confirmation, entries = [item[0] for item in prepared]
    result["aggregation_coverage"] = {tf: item[1] for tf, item in zip((origin_tf, confirmation_tf, entry_tf), prepared)}
    stories = bias.find_stories(origin, confirmation, origin_tf=origin_tf, confirmation_tf=confirmation_tf,
                                as_of=clock, level_mode=level_mode)
    result["stories"] = [asdict(s) for s in stories]
    risk = RiskProfile(stop_profile, pip(pair), buffer_pips, fixed_stop_pips)
    seen, orders = set(), []
    sides_at = {}
    for story in stories:
        sides_at.setdefault(story.available_at, set()).add(story.side)
    for story in stories:
        if len(sides_at[story.available_at]) > 1:
            result["skipped"].append({"origin_at": story.origin_at, "reason": "conflicting_opposite_contexts_at_same_clock"})
            continue
        if story.target is None:
            result["skipped"].append({"origin_at": story.origin_at, "reason": "no_known_directional_origin_target"})
            continue
        end = _context_end(story, source, origin, stories)
        context = Context(story.side, story.available_at, story.origin_tf, story.target,
                          story.target_available_at, story.target_kind, story.target_tf, expires_at=end)
        formed = detect_setups(entries, context, tf=entry_tf, profile=risk, as_of=clock, level_mode=level_mode)
        for setup in formed:
            if setup.available_at < scan:
                continue
            payload = asdict(setup)
            identity = json.dumps(payload, default=_json, sort_keys=True)
            if identity in seen:
                continue
            seen.add(identity)
            key = hashlib.sha256((pair + identity).encode()).hexdigest()[:24]
            order = Order(key, pair, setup.side, setup.tf, setup.profile, setup.entry, setup.stop,
                          setup.target, setup.available_at, setup.available_at + pd.Timedelta(hours=pending_hours),
                          story.side, story.origin_tf, cancel_at=end)
            result["setups"].append(payload)
            orders.append(order)
    result["observations"] = simulate_many(orders, source, as_of=clock, costs=costs)
    result["status"] = "COMPUTED_SUPPORTED_ROUTES"
    result["summary"] = {"stories": len(stories), "setups": len(result["setups"]),
                         "filled": sum(x["status"] == "FILLED" for x in result["observations"]),
                         "censored": sum(x["outcome"] == "CENSORED" for x in result["observations"])}
    # JSON round trip normalizes timestamp fields consistently without mutating events.
    return json.loads(json.dumps(result, default=_json, allow_nan=False))
