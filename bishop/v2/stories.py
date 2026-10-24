"""Causal story routes; no orders, IO, outcomes or source fixture lookup."""
from __future__ import annotations

from dataclasses import dataclass
from .types import Bar, Clock, Event, Story, StrategyPolicy, stable_id

LADDERS = {"M": "W", "W": "D", "D": "H4", "H4": "H1"}
BREAKS = frozenset(("BREAKOUT", "BOS", "SWEEP_BOS", "EXTERNAL_BREAK"))


@dataclass(frozen=True)
class StoryResult:
    stories: tuple[Story, ...]
    events: tuple[Event, ...]
    reactions: tuple[Event, ...]
    support: tuple[dict, ...]


def _close_clock(bar, *available):
    return Clock(bar.end, bar.end, max((bar.available_at,) + available))


def _event(kind, bar, policy, *, side=None, reference_id=None, price=None,
           evidence_ids=(), clock=None, details=None, status="KNOWN"):
    return Event(id=stable_id(kind, bar.id, reference_id, evidence_ids, policy.id),
                 kind=kind, instrument=bar.instrument, tf=bar.tf,
                 clock=clock or _close_clock(bar), side=side,
                 reference_id=reference_id, price_ticks=price, bar_ids=(bar.id,),
                 evidence_ids=evidence_ids, policy_id=policy.id,
                 evidence_status=status, details=details or {})


def _role_qualification(level, result, at):
    changes = sorted((e for e in result.events if e.kind == "LEVEL_ROLE_CHANGE" and
                      e.reference_id == level.id and e.available_at <= at),
                     key=lambda e: (e.available_at, e.id))
    if not changes:
        return None, None, None
    change = changes[-1]
    assessments = sorted((e for e in result.events if e.kind == "IMPULSE_ASSESSMENT" and
                          e.reference_id == change.id and e.available_at <= at and
                          e.evidence_status == "KNOWN"), key=lambda e: (e.available_at, e.id))
    assessment = assessments[-1] if assessments else None
    qualification = (assessment.details.get("qualification") if assessment else
                     change.details.get("qualification"))
    return change, assessment, qualification


def _role(level, result, at, source_profile="bishop_confirmation"):
    from .structure import role_at
    change, assessment, qualification = _role_qualification(level, result, at)
    # Profiles select source alternatives. An optional numerical assessment is
    # an engineering policy; Bishop raw-close routes have no universal gate.
    raw_routes = ("bishop_confirmation", "bishop_direct", "source_all", "all_routes", "owner_aggressive", "aggressive_direct")
    impulse_required = source_profile.startswith(("core", "plug"))
    if change and (impulse_required or source_profile not in raw_routes):
        if qualification != "IMPULSE_CONFIRMED":
            return None
    return role_at(level, result.events, at)


def _role_side(role):
    if isinstance(role, str):
        return {"SUPPORT": "BUY", "RESISTANCE": "SELL", "BUY": "BUY", "SELL": "SELL"}.get(role)
    return getattr(role, "side", None)


def _reaction_candidates(bars_by_tf, structures, policy):
    reactions, support = [], []
    for tf in policy.origin_tfs:
        bars = tuple(b for b in bars_by_tf.get(tf, ()) if b.complete)
        if tf not in structures:
            support.append({"route": "origins", "tf": tf, "status": "UNSUPPORTED", "reason": "missing structure"})
            continue
        level_sets = [(tf, structures[tf])]
        if tf == "D" and "W" in structures:
            level_sets.append(("W", structures["W"]))
        for i, bar in enumerate(bars):
            for level_tf, result in level_sets:
                for level in result.levels:
                    if level.instrument != bar.instrument or level.available_at > bar.start:
                        continue
                    side = _role_side(_role(level, result, bar.start, policy.source_profile))
                    if side is None:
                        if bar.low_ticks <= level.price_ticks <= bar.high_ticks:
                            unavailable = sorted((e for e in result.events if
                                e.kind == "LEVEL_UNAVAILABLE" and e.reference_id == level.id and
                                e.available_at <= bar.start), key=lambda e: (e.available_at, e.id))
                            change, _, qualification = _role_qualification(level, result, bar.start)
                            if unavailable:
                                reason = ("level_unavailable_after_data_gap" if
                                    "GAP" in str(unavailable[0].details.get("reason", "")).upper()
                                    else "level_unavailable")
                            elif change and qualification != "IMPULSE_CONFIRMED":
                                reason = "selected source route requires impulse qualification; raw role change alone is insufficient"
                            else:
                                reason = "level_unavailable"
                            support.append({"route": "reused_level_origin", "level_id": level.id,
                                "origin_bar_id": bar.id, "status": "UNKNOWN", "reason": reason,
                                "unavailability_event_id": unavailable[0].id if unavailable else None})
                        continue
                    rejected = bar.close_ticks > level.price_ticks if side == "BUY" else bar.close_ticks < level.price_ticks
                    if bar.low_ticks <= level.price_ticks <= bar.high_ticks and rejected:
                        change, assessment, qualification = _role_qualification(level, result, bar.start)
                        epoch = change.id if change else level.id
                        role_evidence = (level.id, epoch) + ((assessment.id,) if assessment else ())
                        reactions.append(_event("KL_REJECTION", bar, policy, side=side,
                            reference_id=level.id, price=level.price_ticks, evidence_ids=role_evidence,
                            details={"origin_tf": tf, "level_tf": level_tf, "role_epoch_id": epoch,
                                     "origin_bar_id": bar.id, "fallback": level_tf != tf,
                                     "source_profile": policy.source_profile,
                                     "role_qualification": "IMPULSE_CONFIRMED" if qualification == "IMPULSE_CONFIRMED" else "RAW_CLOSE_BISHOP_ALTERNATIVE" if change else "FORMATION_OR_QUALIFIED",
                                     "impulse_assessment_id": assessment.id if assessment else None,
                                     "role_route_source": "bishop_key_level_close_through" if change else "initial_level_role"}))
            if i and bars[i-1].segment_id == bar.segment_id:
                previous = bars[i-1]
                for side, swept, price in (("BUY", bar.low_ticks < previous.low_ticks and bar.close_ticks > previous.low_ticks, previous.low_ticks),
                                           ("SELL", bar.high_ticks > previous.high_ticks and bar.close_ticks < previous.high_ticks, previous.high_ticks)):
                    if swept:
                        reactions.append(_event("PRIOR_CANDLE_SWEEP", bar, policy, side=side,
                            reference_id=previous.id, price=price, evidence_ids=(previous.id,),
                            details={"origin_tf": tf, "level_tf": None, "origin_bar_id": bar.id, "fallback": False}))
    return reactions, support


def _touch(reaction, origin, lower):
    """First witnessed contact interval; coarse origin alone cannot prove BO order."""
    for bar in lower:
        if not origin.start <= bar.start or bar.end > origin.end:
            continue
        hit = bar.low_ticks <= reaction.price_ticks <= bar.high_ticks
        if reaction.kind == "PRIOR_CANDLE_SWEEP":
            hit = bar.low_ticks < reaction.price_ticks if reaction.side == "BUY" else bar.high_ticks > reaction.price_ticks
        if hit:
            return bar
    return None


def _invalidated(reaction, origin, until, bars, structures):
    for bar in bars:
        if not origin.end < bar.end or bar.available_at > until:
            continue
        if bar.close_ticks < reaction.price_ticks if reaction.side == "BUY" else bar.close_ticks > reaction.price_ticks:
            return True
        if reaction.kind == "KL_REJECTION" and bar.low_ticks <= reaction.price_ticks <= bar.high_ticks:
            # A new same-role reaction must obtain its own positive confirmation.
            return True
    if reaction.kind == "KL_REJECTION":
        result = structures[reaction.details["level_tf"]]
        level = next(l for l in result.levels if l.id == reaction.reference_id)
        if _role_side(_role(level, result, until, reaction.details.get("source_profile", "bishop_confirmation"))) != reaction.side:
            return True
    return False


def _related_reference(event, reference, touch, lower, structure):
    """Prove pre-contact reference or a fresh reference in this reaction leg.

    Newly formed turns alone are insufficient: a frozen range snapshot must
    bind its protected origin to the witnessed contact/post-contact leg and
    bind the broken turn to that same lineage. No nearest-turn substitution.
    """
    ref_available = reference.available_at if reference else event.details.get("reference_available_at")
    if ref_available is None:
        return None
    if ref_available <= touch.start:
        return {"kind": "PRE_REACTION_REFERENCE", "evidence_ids": (event.reference_id, touch.id)}
    if reference is None or reference.formed_at < touch.end or reference.available_at > event.clock.occurred_from:
        return None
    turns = {turn.id: turn for turn in structure.turns}
    bars = {bar.id: bar for bar in lower}
    # Each snapshot is selected only at the break's observation clock. Later
    # range promotion/migration may never create a retrospective relationship.
    versions = {}
    for candidate in structure.ranges:
        if candidate.available_at <= event.available_at:
            previous = versions.get(candidate.id)
            if previous is None or candidate.available_at > previous.available_at:
                versions[candidate.id] = candidate
    for lineage in sorted(versions.values(), key=lambda r: (r.available_at, r.id)):
        is_event_lineage = event.scope_id == lineage.id or lineage.details.get("seed_break_event_id") == event.id
        if not is_event_lineage or lineage.status == "BROKEN" or lineage.direction != event.side:
            continue
        if reference.id not in (lineage.endpoint_turn_id, lineage.protected_turn_id):
            continue
        protected = turns.get(lineage.protected_turn_id)
        protected_bar = bars.get(protected.anchor_bar_id) if protected else None
        if protected_bar is None or protected.available_at > event.available_at:
            continue
        if protected_bar.segment_id != touch.segment_id or protected_bar.start < touch.start:
            continue
        if protected_bar.end > event.clock.occurred_from:
            continue
        # The episode's range origin must itself touch the reaction price or
        # be descended from a parent which already contains that contact.
        same_contact = protected_bar.id == touch.id
        parent = versions.get(lineage.parent_id)
        parent_known = parent is not None and parent.available_at <= touch.start
        if not same_contact and not parent_known:
            continue
        if parent_known:
            low, high = sorted((parent.origin_ticks, parent.endpoint_ticks))
            if not low <= touch.close_ticks <= high:
                continue
            if any(e.kind == "RANGE_BROKEN" and e.scope_id == parent.id and
                   touch.available_at < e.available_at <= event.available_at for e in structure.events):
                continue
        # No other lower-bar segment or opposing break may sever the episode.
        if any(b.segment_id != touch.segment_id for b in lower
               if touch.start <= b.start and b.end <= event.clock.occurred_from):
            continue
        if any(e.kind in BREAKS and e.side != event.side and e.scope_id == lineage.id and
               touch.available_at < e.available_at < event.available_at for e in structure.events):
            continue
        return {"kind": "POST_REACTION_CHILD_REFERENCE",
                "lineage_id": lineage.id, "lineage_version_id": lineage.version_id,
                "parent_lineage_id": lineage.parent_id,
                "evidence_ids": (touch.id, protected.id, reference.id, lineage.version_id)}
    return None


def _confirm(reaction, origin, tf, lower, structure, bars, structures, *, after=None):
    touch = _touch(reaction, origin, lower)
    if touch is None:
        return None
    earliest = max(touch.end, after or touch.end)
    references = {t.id: t for t in structure.turns}
    candidates = []
    for event in structure.events:
        if event.kind not in BREAKS or event.side != reaction.side or event.evidence_status != "KNOWN":
            continue
        if event.clock.occurred_from <= earliest:
            continue
        relation = _related_reference(event, references.get(event.reference_id), touch, lower, structure)
        if relation is None:
            continue
        earlier_break = any(e.kind in BREAKS and e.reference_id == event.reference_id and e.available_at < event.available_at for e in structure.events)
        if earlier_break:
            continue
        available = max(reaction.available_at, event.available_at, touch.available_at)
        if _invalidated(reaction, origin, available, bars, structures):
            continue
        candidates.append((available, event.id, event, touch, relation))
    return min(candidates, default=None, key=lambda x: x[:2])


def _destination(origin_tf, side, price, at, structures, policy):
    result = structures[origin_tf]
    options = [l for l in result.levels if l.available_at <= at and
               _role_side(_role(l, result, at, policy.source_profile)) == ("SELL" if side == "BUY" else "BUY") and
               (l.price_ticks > price if side == "BUY" else l.price_ticks < price)]
    return min(options, key=lambda l: (abs(l.price_ticks-price), l.available_at, l.id), default=None)


def find_stories(bars_by_tf, structures, policy=StrategyPolicy()):
    """Publish immutable initial stories and later lifecycle observations.

    Inputs must contain only available complete bars from a frozen causal feed.
    Stories retain their initial state; later changes are append-only events.
    """
    bars_by_tf = {tf: tuple(sorted((b for b in bars if b.complete), key=lambda b: b.end))
                  for tf, bars in bars_by_tf.items()}
    for tf, bars in bars_by_tf.items():
        if any(b.tf != tf for b in bars):
            raise ValueError("bar timeframe does not match its input key")
        if any(a.end > b.start for a, b in zip(bars, bars[1:])):
            raise ValueError("overlapping story input bars")
    instruments = {b.instrument for bars in bars_by_tf.values() for b in bars}
    if len(instruments) > 1:
        raise ValueError("story analysis requires one instrument")
    bar_map = {b.id: b for bars in bars_by_tf.values() for b in bars}
    reactions, support = _reaction_candidates(bars_by_tf, structures, policy)
    stories, events = [], []
    for reaction in reactions:
        origin = bar_map[reaction.details["origin_bar_id"]]
        tf = LADDERS.get(origin.tf)
        if tf not in structures or tf not in bars_by_tf:
            support.append({"route": reaction.kind, "tf": origin.tf, "status": "UNSUPPORTED", "reason": "missing confirmation timeframe"})
            continue
        fallback = reaction.details["fallback"]
        if fallback:
            weekly = [r for r in reactions if r.tf == "W" and r.kind == "KL_REJECTION" and
                      r.reference_id == reaction.reference_id and r.side == reaction.side and r.available_at <= reaction.available_at]
            if not weekly:
                continue
            count = max(policy.fallback_rejections, 2 if "plug" in policy.source_profile else 1)
            daily = [r for r in reactions if r.tf == "D" and r.reference_id == reaction.reference_id and
                     r.side == reaction.side and r.details.get("role_epoch_id") == reaction.details.get("role_epoch_id") and
                     weekly[-1].available_at <= r.available_at <= reaction.available_at]
            required_bars = list(bars_by_tf["D"])
            idx = required_bars.index(origin)
            expected_ids = {b.id for b in required_bars[max(0, idx-count+1):idx+1]}
            counted = [r for r in daily if r.details["origin_bar_id"] in expected_ids]
            if len({r.details["origin_bar_id"] for r in counted}) < count:
                continue
        answer = _confirm(reaction, origin, tf, bars_by_tf[tf], structures[tf], bars_by_tf[origin.tf], structures)
        route = "weekly_level_daily_fallback" if fallback else "kl_structural" if reaction.kind == "KL_REJECTION" else "candle_sweep_structural"
        intermediate = None
        if origin.tf == "W" and "H4" in structures and "H4" in bars_by_tf:
            # Explicit W rejection -> D engulf -> H4 structure cascade.
            daily = bars_by_tf["D"]
            touch = _touch(reaction, origin, daily)
            if touch:
                for i, current in enumerate(daily):
                    if not i or current.end <= touch.end:
                        continue
                    previous = daily[i-1]
                    engulf = (current.close_ticks > previous.open_ticks and current.open_ticks <= previous.close_ticks and previous.side == "SELL" and current.side == "BUY") if reaction.side == "BUY" else (current.close_ticks < previous.open_ticks and current.open_ticks >= previous.close_ticks and previous.side == "BUY" and current.side == "SELL")
                    if not engulf:
                        continue
                    # Terminal relation still uses original Weekly reaction;
                    # the structural close must follow the engulf occurrence.
                    cascade = _confirm(reaction, origin, "H4", bars_by_tf["H4"], structures["H4"], bars_by_tf[origin.tf], structures, after=current.end)
                    if cascade and (answer is None or (max(cascade[0], current.available_at), cascade[1]) < answer[:2]):
                        answer = cascade
                        intermediate = _event("ENGULF_CONTEXT", current, policy, side=reaction.side,
                                              evidence_ids=(reaction.id, previous.id),
                                              details={"definition": "body_engulf_v1_implementation_choice"})
                        events.append(intermediate)
                        route, tf = "weekly_daily_engulf_h4_cascade", "H4"
                        break
        if answer is None:
            support.append({"reaction_id": reaction.id, "route": route, "status": "WAIT_CONFIRMATION", "reason": "no fresh related structural break with known ordering/reference"})
            continue
        available, _, confirmation, touch, relation = answer
        if intermediate:
            available = max(available, intermediate.available_at)
        if fallback:
            # The fallback is only a fallback while W has no related D break.
            weekly_origin = bar_map[weekly[-1].details["origin_bar_id"]]
            parent_confirmation = _confirm(weekly[-1], weekly_origin, "D", bars_by_tf["D"], structures["D"], bars_by_tf["W"], structures)
            if parent_confirmation and parent_confirmation[0] <= available:
                continue
        current_bars = [b for b in bars_by_tf[origin.tf] if b.available_at <= available]
        current_price = current_bars[-1].close_ticks
        target = _destination(origin.tf, reaction.side, current_price, available, structures, policy)
        relation_event = _event("REACTION_CONFIRMATION_LINK", origin, policy, side=reaction.side,
            reference_id=confirmation.id, evidence_ids=(reaction.id, confirmation.id) + relation["evidence_ids"],
            clock=Clock(confirmation.clock.occurred_from, confirmation.clock.occurred_to, available),
            details=relation)
        events.append(relation_event)
        evidence = (reaction.id, touch.id, confirmation.id, relation_event.id) + ((intermediate.id,) if intermediate else ())
        ranges = [r for r in structures[tf].ranges if r.available_at <= available and
                  (r.id == confirmation.scope_id or r.details.get("seed_break_event_id") == confirmation.id)]
        scoped_range = max(ranges, key=lambda r: r.available_at, default=None)
        story = Story(id=stable_id("story", evidence, route, policy.id), instrument=origin.instrument,
                      side=reaction.side, origin_tf=origin.tf, level_tf=reaction.details["level_tf"],
                      confirmation_tf=tf, route=route, source_profile=policy.source_profile,
                      clock=Clock(confirmation.clock.occurred_from, confirmation.clock.occurred_to, available),
                      origin_id=reaction.id, confirmation_id=confirmation.id,
                      level_id=reaction.reference_id if reaction.kind == "KL_REJECTION" else None,
                      scope_id=scoped_range.id if scoped_range else confirmation.scope_id, destination_ticks=target.price_ticks if target else None,
                      destination_ref_id=target.id if target else None, evidence_ids=evidence,
                      details={"policy_id": policy.id, "reaction_bar_id": origin.id,
                               "role_epoch_id": reaction.details.get("role_epoch_id"),
                               "role_qualification": reaction.details.get("role_qualification"),
                               "role_route_source": reaction.details.get("role_route_source"),
                               "destination_policy": "nearest_known_opposing_origin_kl_v1",
                               "intermediate_tf": "D" if intermediate else None,
                               "confirmation_relation": relation["kind"],
                               "confirmation_lineage_id": relation.get("lineage_id"),
                               "protected_origin_status": "KNOWN" if scoped_range and scoped_range.status == "DEFINED" else "UNKNOWN",
                               "protected_turn_id": scoped_range.protected_turn_id if scoped_range else None,
                               "scope_type": scoped_range.details.get("scope_type") if scoped_range else "LOCAL",
                               "initial_weekly_relation": "UNKNOWN"})
        stories.append(story)
    stories.sort(key=lambda s: (s.available_at, s.id))
    # Weekly snapshots use only information already known at each eligibility.
    from dataclasses import replace
    decorated = []
    for story in stories:
        weekly = [s for s in stories if s.instrument == story.instrument and s.origin_tf == "W" and s.available_at < story.available_at]
        parent = weekly[-1] if weekly else None
        relation = "ALIGNED" if parent and parent.side == story.side else "COUNTER_WEEKLY" if parent else "UNKNOWN"
        decorated.append(replace(story, parent_id=parent.id if parent else None,
            details={**story.details, "initial_weekly_relation": relation,
                     "owner_selection": "BLOCKED_COUNTERWEEKLY" if relation == "COUNTER_WEEKLY" and not policy.allow_counterweekly else "CANDIDATE",
                     "counterweekly_target_guard_required": relation == "COUNTER_WEEKLY"}))
    stories = decorated
    reaction_map = {r.id: r for r in reactions}
    for story in stories:
        for bar in bars_by_tf[story.origin_tf]:
            if bar.start < story.available_at:
                continue
            if story.destination_ticks is not None and bar.low_ticks <= story.destination_ticks <= bar.high_ticks:
                events.append(_event("STORY_DESTINATION_REACHED", bar, policy, side=story.side,
                    reference_id=story.id, price=story.destination_ticks, clock=bar.clock,
                    evidence_ids=(story.id, story.destination_ref_id),
                    details={"pending_action": "CANCEL_DEPENDENT", "position_action": "NONE"}))
                break
        for successor in stories:
            if successor.instrument != story.instrument or successor.side == story.side or successor.available_at <= story.available_at:
                continue
            r = reaction_map[successor.origin_id]
            if successor.origin_tf == story.origin_tf and successor.details.get("scope_type") == story.details.get("scope_type") and story.details.get("scope_type") in ("ROOT", "CHILD"):
                # Positive opposite origin/confirmation, same story scope.
                kind = "STORY_FLIPPED" if r.reference_id == story.destination_ref_id and r.kind == "KL_REJECTION" else "OPPOSITE_STORY_CONFIRMED"
            else:
                kind = "STORY_RETRACEMENT_EVIDENCE"
            origin = bar_map[successor.details["reaction_bar_id"]]
            events.append(_event(kind, origin, policy, side=successor.side,
                reference_id=story.id, evidence_ids=(story.id, successor.id), clock=successor.clock,
                details={"successor_story_id": successor.id,
                         "pending_action": "CANCEL_DEPENDENT" if kind == "STORY_FLIPPED" else "REASSESS_SETUP_DEPENDENCIES",
                         "position_action": "NONE"}))
            if kind == "STORY_FLIPPED":
                break
        for observation in structures[story.confirmation_tf].events:
            if observation.kind == "RANGE_BROKEN" and observation.scope_id == story.scope_id and observation.available_at > story.available_at:
                events.append(Event(id=stable_id("story_invalidated", story.id, observation.id, policy.id),
                    kind="STORY_INVALIDATED", instrument=story.instrument, tf=story.origin_tf,
                    side=story.side, clock=observation.clock, reference_id=story.id,
                    evidence_ids=(story.id, observation.id), policy_id=policy.id,
                    details={"pending_action": "CANCEL_DEPENDENT", "position_action": "NONE",
                             "opposite_direction_confirmed": False}))
                break
    support.extend(({"route": "engulf_started_previous_story_exception", "status": "UNSUPPORTED", "reason": "source exception does not establish executable scope/geometry"},
                    {"route": "experience_based_no_daily_structure", "status": "UNSUPPORTED", "reason": "discretionary source route lacks positive mechanical Daily evidence"},
                    {"route": "protected_story_origin", "status": "KNOWN" if stories and all(s.details.get("protected_origin_status") == "KNOWN" for s in stories) else "UNKNOWN", "reason": "DEFINED scoped lineage required; no reaction wick substitution"}))
    return StoryResult(tuple(stories), tuple(sorted(events, key=lambda e: (e.available_at, e.id))),
                       tuple(reactions), tuple(support))
