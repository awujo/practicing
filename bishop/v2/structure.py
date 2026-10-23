"""Causal close-line objects and explicitly scoped advanced ranges.

Numerical interpretation: knowledge-base/study/build_structure_contract.md.
No broker IO, historical fixtures, future pivots, or universal impulse filter.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from bisect import bisect_right
from datetime import datetime
from types import MappingProxyType
from typing import Mapping, Any

from .types import Bar, Clock, Event, Turn, Level, Liquidity, StrategyPolicy, stable_id, utc


@dataclass(frozen=True)
class Range:
    id: str
    parent_id: str | None
    direction: str
    status: str
    protected_turn_id: str
    protected_liquidity_id: str | None
    endpoint_turn_id: str
    endpoint_liquidity_id: str | None
    origin_ticks: int
    endpoint_ticks: int
    formed_at: datetime
    available_at: datetime
    version_id: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    @property
    def side(self):
        return self.direction


@dataclass(frozen=True)
class StructureResult:
    turns: tuple[Turn, ...]
    levels: tuple[Level, ...]
    liquidity: tuple[Liquidity, ...]
    events: tuple[Event, ...]
    ranges: tuple[Range, ...]


class RoleIndex:
    """Per-level causal role timelines; build once, query in logarithmic time."""

    def __init__(self, events):
        grouped = {}
        for event in events:
            if event.kind == "LEVEL_ROLE_CHANGE" and event.reference_id is not None:
                grouped.setdefault(event.reference_id, []).append(event)
        self._timeline = MappingProxyType({
            key: (tuple(e.available_at for e in ordered), tuple(e.side for e in ordered))
            for key, rows in grouped.items()
            for ordered in (sorted(rows, key=lambda e: (e.available_at, e.id)),)
        })

    def role_at(self, level: Level, as_of):
        at = utc(as_of)
        if level.available_at > at:
            return None
        times, sides = self._timeline.get(level.id, ((), ()))
        position = bisect_right(times, at)
        return sides[position-1] if position else level.side


def role_at(level: Level, events, as_of):
    """Return BUY/support or SELL/resistance known at as_of; None if unborn.

    Raw body breaks change the potential retest role. Models requiring impulse
    must separately qualify it; a role is never a structural/story assertion.
    """
    if isinstance(events, RoleIndex):
        return events.role_at(level, as_of)
    at = utc(as_of)
    if level.available_at > at:
        return None
    side = level.side
    for event in sorted(events, key=lambda e: (e.available_at, e.id)):
        if event.available_at <= at and event.reference_id == level.id and event.kind == "LEVEL_ROLE_CHANGE":
            side = event.side
    return side


def analyze(bars, policy=StrategyPolicy(), *, supplemental_liquidity=()) -> StructureResult:
    bars = tuple(bars)
    supplemental = tuple(supplemental_liquidity)
    if any(not isinstance(pool, Liquidity) for pool in supplemental):
        raise ValueError("supplemental liquidity must use Liquidity records")
    if len({pool.id for pool in supplemental}) != len(supplemental):
        raise ValueError("duplicate supplemental liquidity IDs")
    if any(not isinstance(b, Bar) or not b.complete for b in bars):
        raise ValueError("structure requires complete Bar records")
    for left, right in zip(bars, bars[1:]):
        if (left.instrument, left.tf) != (right.instrument, right.tf):
            raise ValueError("structure input must have one instrument/timeframe")
        if left.end > right.start or left.end >= right.end:
            raise ValueError("bars must be chronological, unique and nonoverlapping")
    if bars and any((pool.instrument, pool.tf) != (bars[0].instrument, bars[0].tf)
                    for pool in supplemental):
        raise ValueError("supplemental liquidity must match structure instrument/timeframe")
    turns, levels, pools, events, ranges = [], [], [], [], []
    known_turns, known_levels, known_pools = [], [], list(supplemental)
    broken = set()
    roles = {}
    active = {}  # lineage id -> current immutable version
    seeds = {}  # (scope, side, swept reference, frozen target, leg epoch)
    flow = {}
    prior = None
    direction = 0
    plateau_start = 0
    segment_start = 0
    turn_by_id = {}
    pool_by_turn = {}
    local_refs = {}

    def emit(kind, bar, *, side=None, ref=None, scope=None, evidence=(), details=None, wick=False):
        extra = dict(details or {})
        if ref is not None:
            extra.update(reference_formed_at=ref.formed_at,
                         reference_available_at=ref.available_at)
        extra.setdefault("scope_type", "LOCAL" if scope is None else "CHILD" if active.get(scope) and active[scope].parent_id else "ROOT")
        deps = [bar.available_at]
        if ref is not None:
            deps.append(ref.available_at)
        clock = Clock(bar.start if wick else bar.end, bar.end, max(deps), "BAR" if wick else "EXACT")
        event = Event(id=stable_id("structure_event", policy.id, kind, bar.id,
                                  ref.id if ref else None, scope, tuple(evidence)),
                      kind=kind, instrument=bar.instrument, tf=bar.tf, clock=clock,
                      side=side, reference_id=ref.id if ref else None,
                      price_ticks=ref.price_ticks if ref else None, scope_id=scope,
                      bar_ids=(bar.id,), evidence_ids=tuple(evidence),
                      policy_id=policy.id, details=extra)
        events.append(event)
        return event

    def snapshot(r, bar, **changes):
        details = changes.pop("details", dict(r.details))
        known_at = max(bar.available_at, r.available_at, changes.pop("available_at", bar.available_at))
        result = replace(r, available_at=known_at,
                         version_id=stable_id("range_version", policy.id, r.id, bar.id, changes, details),
                         details=details, **changes)
        active[r.id] = result
        ranges.append(result)
        return result

    def classify(ref, bar):
        high = ref.kind in ("H", "HIGH")
        p = ref.price_ticks
        if bar.close_ticks > p if high else bar.close_ticks < p:
            return "BREAK", "BUY" if high else "SELL"
        if bar.high_ticks > p >= bar.close_ticks if high else bar.low_ticks < p <= bar.close_ticks:
            # An entirely gapped bar cannot sweep a price it never visited.
            if bar.low_ticks <= p <= bar.high_ticks:
                return "SWEEP", "SELL" if high else "BUY"
        if bar.low_ticks <= p <= bar.high_ticks:
            return "TOUCH", "SELL" if high else "BUY"
        return None, None

    def pool_for(turn):
        return pool_by_turn.get(turn.id)

    def containing(origin, target):
        matches = [r for r in active.values() if r.status != "BROKEN"
                   and min(r.origin_ticks, r.endpoint_ticks) < min(origin, target)
                   and max(origin, target) < max(r.origin_ticks, r.endpoint_ticks)]
        return min(matches, key=lambda r: (abs(r.endpoint_ticks-r.origin_ticks), r.id)) if matches else None

    def make_range(bar, side, origin, target, event, seed=None):
        parent = active.get(seed["parent_id"]) if seed and seed.get("parent_id") else containing(origin.price_ticks, target.price_ticks)
        if parent and parent.status == "BROKEN":
            return None
        # A new seed at the same nonnested scope replaces provisional state.
        for old in list(active.values()):
            if old.parent_id == (parent.id if parent else None) and old.status == "PROVISIONAL_BREAKOUT":
                snapshot(old, bar, status="BROKEN", details={**old.details, "reason": "SUPERSEDED"})
        if parent is None and any(r.parent_id is None and r.status == "DEFINED" for r in active.values()):
            return None  # unrelated local seed cannot replace a protected root
        rid = stable_id("range", policy.id, event.id, origin.id, parent.id if parent else None)
        op, ep = pool_for(origin), pool_for(target)
        r = Range(rid, parent.id if parent else None, side,
                  "DEFINED" if seed else "PROVISIONAL_BREAKOUT", origin.id,
                  op.id if op else None, target.id, ep.id if ep else None,
                  origin.price_ticks, target.price_ticks, bar.end, bar.available_at,
                  stable_id("range_version", policy.id, rid, bar.id),
                  {"seed_break_event_id": event.id,
                   "seed_sweep_event_id": seed["event"].id if seed else None,
                   "scope_type": "CHILD" if parent else "ROOT",
                   "endpoint_stage": "SEED_REFERENCE", "epoch_start": bar.end,
                   "candidate_id": None, "sweep_id": None,
                   "sweep_wick_ticks": seed["wick"] if seed else None})
        active[r.id] = r
        ranges.append(r)
        return r

    for i, bar in enumerate(bars):
        discontinuity = prior is not None and (bar.segment_id != prior.segment_id)
        if discontinuity:
            for r in list(active.values()):
                if r.status != "BROKEN":
                    snapshot(r, bar, status="BROKEN", details={**r.details, "reason": "DATA_GAP"})
            seeds.clear()
            local_refs.clear()
            flow.clear()
            known_turns.clear()
            known_levels.clear()
            # Pre-gap pools have uncertain consumption; future pools remain
            # causal candidates and must not disappear with local pivot state.
            known_pools[:] = [pool for pool in supplemental
                              if pool.available_at >= bar.start and pool.id not in broken]
            prior, direction, plateau_start, segment_start = None, 0, i, i
        # A reference revealed by a close can first inspect the following bar.
        eligible_turns = [t for t in known_turns if t.available_at <= bar.start]
        eligible_levels = [l for l in known_levels if l.available_at <= bar.start]
        eligible_pools = [p for p in known_pools if p.available_at <= bar.start]
        local_refs = {}
        for t in eligible_turns:
            local_refs[t.kind] = t
        primitive = {}
        # Raw wick-pool observations never substitute for close structure.
        for ref in eligible_pools:
            if ref.id in broken:
                continue
            kind, side = classify(ref, bar)
            if kind:
                ev = emit("LIQUIDITY_" + kind, bar, side=side, ref=ref, wick=kind != "BREAK",
                          details={"reference_type": "LIQUIDITY", "intrabar_order": "UNKNOWN"})
                primitive[ref.id] = ev
                if kind == "BREAK" or kind == "SWEEP":
                    broken.add(ref.id)
        # Keep only standing pools in the working set; immutable history remains
        # in the result. A delayed pool is retained until available.
        known_pools[:] = [p for p in known_pools if p.id not in broken]
        for level in eligible_levels:
            side = roles.get(level.id, level.side)
            p = level.price_ticks
            is_break = bar.close_ticks < p if side == "BUY" else bar.close_ticks > p
            if is_break:
                new_side = "SELL" if side == "BUY" else "BUY"
                ev = emit("LEVEL_BREAK", bar, side=new_side, ref=level,
                          details={"crossing_mode": "GAP" if not bar.low_ticks <= p <= bar.high_ticks else "TRADED"})
                emit("LEVEL_ROLE_CHANGE", bar, side=new_side, ref=level, evidence=(ev.id,),
                     details={"old_role": side, "new_role": new_side, "qualification": "RAW_BREAK"})
                roles[level.id] = new_side
            elif bar.low_ticks <= p <= bar.high_ticks:
                sweep = bar.low_ticks < p if side == "BUY" else bar.high_ticks > p
                emit("LEVEL_SWEEP" if sweep else "LEVEL_TOUCH", bar, side=side, ref=level, wick=True)
        local_sweeps = []
        local_breaks = []
        for ref in local_refs.values():
            kind, side = classify(ref, bar)
            if kind == "BREAK" and ref.id not in broken:
                old_flow = flow.get(None)
                name = "BOS" if old_flow and old_flow != side else "BREAKOUT"
                event = emit(name, bar, side=side, ref=ref,
                             details={"reference_type": "TURN", "crossing_mode": "GAP" if not bar.low_ticks <= ref.price_ticks <= bar.high_ticks else "TRADED"})
                local_breaks.append((ref, event))
                broken.add(ref.id)
                flow[None] = side
            elif kind == "SWEEP" and ref.id not in broken:
                ev = emit("SWEEP", bar, side=side, ref=ref, wick=True,
                          details={"reference_type": "TURN", "intrabar_order": "UNKNOWN"})
                local_sweeps.append((ref, ev))
        # Advance frozen sweep candidates before accepting this bar's new sweeps.
        for key, seed in list(seeds.items()):
            side = key[1]
            if key[0] is not None and active[key[0]].status == "BROKEN":
                del seeds[key]
                continue
            lower = bar.close_ticks < seed["extreme"] if side == "BUY" else bar.close_ticks > seed["extreme"]
            if lower or bar.close_ticks == seed["extreme"]:
                seed["extreme"] = bar.close_ticks
                seed["extreme_bar"] = bar.id
            seed["wick"] = min(seed["wick"], bar.low_ticks) if side == "BUY" else max(seed["wick"], bar.high_ticks)
            origins = [t for t in eligible_turns if t.kind == ("L" if side == "BUY" else "H")
                       and t.anchor_bar_id == seed["extreme_bar"]]
            close_break = bar.close_ticks > seed["target"].price_ticks if side == "BUY" else bar.close_ticks < seed["target"].price_ticks
            if close_break and bar.start >= seed["event"].available_at and origins:
                ev = emit("SWEEP_BOS", bar, side=side, ref=seed["target"],
                          evidence=(seed["event"].id, origins[-1].id),
                          details={"reference_type": "TURN", "sweep_event_id": seed["event"].id,
                                   "sweep_reference_id": seed["reference_id"],
                                   "sweep_leg_id": seed["leg_id"],
                                   "parent_range_id": seed["parent_id"]})
                make_range(bar, side, origins[-1], seed["target"], ev, seed)
                del seeds[key]
            elif close_break:
                # A delivered target without a known origin cannot become a
                # future backdated defined seed.
                del seeds[key]
        # Scoped protected-origin, endpoint, and migration transitions.
        for r in list(active.values()):
            if r.status == "BROKEN" or r.available_at > bar.start:
                continue
            origin = turn_by_id[r.protected_turn_id]
            endpoint = turn_by_id[r.endpoint_turn_id]
            origin_break = bar.close_ticks < r.origin_ticks if r.direction == "BUY" else bar.close_ticks > r.origin_ticks
            if origin_break:
                ev = emit("RANGE_BROKEN", bar, side="SELL" if r.direction == "BUY" else "BUY", ref=origin,
                          scope=r.id, details={"old_origin_id": origin.id})
                emit("BOS", bar, side=ev.side, ref=origin, scope=r.id, evidence=(ev.id,))
                snapshot(r, bar, status="BROKEN", details={**r.details, "reason": "PROTECTED_BODY_BREAK"})
                descendants = {r.id}
                for child in list(active.values()):
                    if child.parent_id in descendants and child.status != "BROKEN":
                        descendants.add(child.id)
                        snapshot(child, bar, status="BROKEN", details={**child.details, "reason": "PARENT_BROKEN"})
                continue
            extreme_break = bar.close_ticks > r.endpoint_ticks if r.direction == "BUY" else bar.close_ticks < r.endpoint_ticks
            endpoint_sweep = bar.high_ticks > r.endpoint_ticks >= bar.close_ticks if r.direction == "BUY" else bar.low_ticks < r.endpoint_ticks <= bar.close_ticks
            d = dict(r.details)
            candidate = turn_by_id.get(d.get("candidate_id"))
            candidate_broken = candidate is not None and (
                bar.close_ticks < candidate.price_ticks if r.direction == "BUY"
                else bar.close_ticks > candidate.price_ticks)
            if candidate_broken:
                d.update(candidate_id=None, sweep_id=None)
                candidate = None
                r = snapshot(r, bar, details=d)
            if extreme_break and not d.get("endpoint_broken"):
                ev = emit("EXTERNAL_BREAK", bar, side=r.direction, ref=endpoint, scope=r.id,
                          details={"old_origin_id": origin.id, "candidate_id": candidate.id if candidate else None})
                if candidate and d.get("sweep_id") and d.get("sweep_available_at") <= bar.start:
                    cp = pool_for(candidate)
                    emit("ORIGIN_PROMOTED", bar, side=r.direction, ref=candidate, scope=r.id,
                         evidence=(ev.id, d["sweep_id"]), details={"old_origin_id": origin.id, "new_origin_id": candidate.id})
                    d.update(candidate_id=None, sweep_id=None, endpoint_broken=True, epoch_start=bar.end,
                             migration_pending_evidence=False)
                    snapshot(r, bar, protected_turn_id=candidate.id,
                             protected_liquidity_id=cp.id if cp else None,
                             origin_ticks=candidate.price_ticks, details=d)
                else:
                    d.update(endpoint_broken=True, epoch_start=bar.end,
                             migration_pending_evidence=True)
                    snapshot(r, bar, details=d)
            elif endpoint_sweep and bar.low_ticks <= endpoint.price_ticks <= bar.high_ticks:
                emit("EXTERNAL_SWEEP", bar, side="SELL" if r.direction == "BUY" else "BUY", ref=endpoint, scope=r.id,
                     wick=True, details={"old_origin_id": origin.id, "candidate_id": candidate.id if candidate else None,
                                         "protected_origin_retained": True})
            # Linked continuation sweep must happen after candidate becomes
            # known, against the pullback-side reference, inside this range.
            elif candidate:
                for ref, ev in local_sweeps:
                    if ev.side == r.direction and candidate.available_at <= bar.start and ev.available_at > candidate.available_at:
                        d.update(sweep_id=ev.id, sweep_available_at=ev.available_at)
                        snapshot(r, bar, details=d)
                        break
        # New seeds see frozen pre-sweep opposite reference; same-bar break is
        # not evidence that the sweep happened first.
        for ref, ev in local_sweeps:
            target = local_refs.get("H" if ev.side == "BUY" else "L")
            if target and (target.price_ticks > ref.price_ticks if ev.side == "BUY" else target.price_ticks < ref.price_ticks):
                parent = containing(ref.price_ticks, target.price_ticks)
                parent_id = parent.id if parent else None
                epoch = parent.details["epoch_start"] if parent else target.id
                leg_id = stable_id("sweep_leg", policy.id, parent_id, ev.side, ref.id, target.id, epoch)
                key = (parent_id, ev.side, ref.id, target.id, epoch)
                seeds[key] = {"event": ev, "target": target,
                    "reference_id": ref.id, "leg_id": leg_id,
                    "parent_id": parent_id, "extreme": bar.close_ticks, "extreme_bar": bar.id,
                    "wick": bar.low_ticks if ev.side == "BUY" else bar.high_ticks}
        for ref, ev in local_breaks:
            opposite = local_refs.get("L" if ev.side == "BUY" else "H")
            if opposite and not any(r.status != "BROKEN" and r.parent_id is None for r in active.values()):
                make_range(bar, ev.side, opposite, ref, ev)
        # Publish objects only after all this bar's observations/transitions.
        new_turn = None
        if prior is not None:
            change = (bar.close_ticks > prior.close_ticks) - (bar.close_ticks < prior.close_ticks)
            if change and direction and change != direction:
                anchor = prior
                kind = "H" if direction > 0 else "L"
                interval = bars[plateau_start:i]
                evidence_bars = bars[max(segment_start, plateau_start-1):i+1]
                available = max(b.available_at for b in evidence_bars)
                new_turn = Turn(id=stable_id("turn", policy.id, kind, anchor.id, bar.id),
                    instrument=bar.instrument, tf=bar.tf, kind=kind, price_ticks=anchor.close_ticks,
                    formed_at=anchor.end, available_at=available, anchor_bar_id=anchor.id,
                    confirmation_bar_id=bar.id, bar_ids=tuple(b.id for b in evidence_bars),
                    details={"policy_id": policy.id, "plateau_start": interval[0].end})
                turns.append(new_turn)
                turn_by_id[new_turn.id] = new_turn
                prior_turn = known_turns[-1] if known_turns else None
                if prior_turn:
                    start_index = next(j for j in range(segment_start, i) if bars[j].id == prior_turn.anchor_bar_id)
                    leg = bars[start_index:i+1]
                    price = max(b.high_ticks for b in leg) if kind == "H" else min(b.low_ticks for b in leg)
                    pool = Liquidity(id=stable_id("turn_pool", policy.id, new_turn.id), instrument=bar.instrument,
                        tf=bar.tf, kind="HIGH" if kind == "H" else "LOW", price_ticks=price,
                        formed_at=anchor.end, available_at=max(available, *(b.available_at for b in leg)),
                        form="TURN_LEG", bar_ids=tuple(b.id for b in leg), policy_id=policy.id,
                        details={"turn_id": new_turn.id})
                    pools.append(pool)
                    known_pools.append(pool)
                    pool_by_turn[new_turn.id] = pool
                known_turns.append(new_turn)
                level = Level(id=stable_id("level", policy.id, new_turn.id), instrument=bar.instrument, tf=bar.tf,
                    kind="A" if kind == "H" else "V", price_ticks=new_turn.price_ticks,
                    side="SELL" if kind == "H" else "BUY", formed_at=new_turn.formed_at,
                    available_at=new_turn.available_at, bar_ids=new_turn.bar_ids, policy_id=policy.id,
                    details={"turn_id": new_turn.id, "formation": "CLOSE_TURN"})
                levels.append(level)
                known_levels.append(level)
            if change:
                direction = change
                plateau_start = i
            if prior.side and prior.side == bar.side and abs(prior.close_ticks-bar.open_ticks) <= policy.oc_gap_ticks:
                level = Level(id=stable_id("oc", policy.id, prior.id, bar.id), instrument=bar.instrument,
                    tf=bar.tf, kind="OC", price_ticks=prior.close_ticks, side=bar.side,
                    formed_at=prior.end, available_at=max(prior.available_at, bar.available_at),
                    bar_ids=(prior.id, bar.id), policy_id=policy.id,
                    details={"junction_gap_ticks": bar.open_ticks-prior.close_ticks})
                levels.append(level)
                known_levels.append(level)
        if new_turn:
            for r in list(active.values()):
                if r.status == "BROKEN":
                    continue
                d = dict(r.details)
                delivery_kind = "H" if r.direction == "BUY" else "L"
                if new_turn.kind == delivery_kind and (d.get("endpoint_broken") or d.get("endpoint_stage") == "SEED_REFERENCE"):
                    farther = new_turn.price_ticks > r.endpoint_ticks if r.direction == "BUY" else new_turn.price_ticks < r.endpoint_ticks
                    if farther:
                        ep = pool_for(new_turn)
                        d.update(endpoint_stage="CONFIRMED_DELIVERY", endpoint_broken=False,
                                 candidate_id=None, sweep_id=None, epoch_start=new_turn.formed_at)
                        snapshot(r, bar, available_at=new_turn.available_at, endpoint_turn_id=new_turn.id,
                                 endpoint_liquidity_id=ep.id if ep else None,
                                 endpoint_ticks=new_turn.price_ticks, details=d)
                elif new_turn.kind != delivery_kind and new_turn.formed_at > d["epoch_start"]:
                    inside = min(r.origin_ticks, r.endpoint_ticks) < new_turn.price_ticks < max(r.origin_ticks, r.endpoint_ticks)
                    if inside:
                        d.update(candidate_id=new_turn.id, sweep_id=None)
                        snapshot(r, bar, available_at=new_turn.available_at, details=d)
        for kind, price in (("HIGH", bar.high_ticks), ("LOW", bar.low_ticks)):
            pool = Liquidity(id=stable_id("bar_pool", policy.id, bar.id, kind),
                instrument=bar.instrument, tf=bar.tf, kind=kind, price_ticks=price,
                formed_at=bar.end, available_at=bar.available_at, form="BAR",
                bar_ids=(bar.id,), policy_id=policy.id,
                details={"source_bar_id": bar.id, "standing_at_formation": True})
            pools.append(pool)
            known_pools.append(pool)
            if bar.tf in ("D", "W", "M"):
                period_pool = Liquidity(id=stable_id("period_pool", policy.id, bar.id, kind),
                    instrument=bar.instrument, tf=bar.tf, kind=kind, price_ticks=price,
                    formed_at=bar.end, available_at=bar.available_at, form="PRIOR_PERIOD",
                    bar_ids=(bar.id,), policy_id=policy.id,
                    details={"period_tf": bar.tf, "source_bar_id": bar.id,
                             "calendar_ownership": "FEED_ADAPTER"})
                pools.append(period_pool)
                known_pools.append(period_pool)
        prior = bar
    if bars:
        horizon = max(bar.available_at for bar in bars)
        pools.extend(pool for pool in supplemental if pool.available_at <= horizon)
    return StructureResult(tuple(turns), tuple(levels), tuple(pools), tuple(events), tuple(ranges))
