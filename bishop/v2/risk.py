"""Causal protection and target alternatives; all numerical defaults are OUR CHOICE."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from .types import Instrument, StrategyPolicy


@dataclass(frozen=True)
class RiskResult:
    stop_ticks: int | None
    target_ticks: int | None
    status: str
    details: dict


def plan(side, entry, at, tf, bars, levels, liquidity, story, instrument: Instrument,
         policy: StrategyPolicy, *, role_lookup=None, protection_bars=(), ranges=(), zone_bounds=None,
         protection_evidence_ids=(), protection_range_ids=()):
    sign = 1 if side == 'BUY' else -1
    bars=tuple(bars)
    visible=[i for i,b in enumerate(bars) if b.complete and b.available_at<=at]
    known_bars=[]
    segment=bars[visible[-1]].segment_id if visible else None
    if visible:
        # Walk the original sequence, not a list with unpublished rows removed.
        # Scheduled closures have no rows and preserve their declared segment.
        for i in range(visible[-1],-1,-1):
            bar=bars[i]
            if not bar.complete or bar.available_at>at or bar.segment_id!=segment:
                break
            known_bars.append(bar)
        known_bars.reverse()
    segment_start=known_bars[0].start if known_bars else None
    excluded=[]
    def current(obj):
        return obj.available_at<=at and (segment_start is None or obj.formed_at>=segment_start)
    def standing(pool):
        if not current(pool):
            return False
        # A target/protective pool cannot be called intact through an observed
        # take or an overlapping receipt interval. Its own formation bars are
        # evidence of the extreme, not a later consumption of that extreme.
        for bar in known_bars:
            if bar.id in pool.bar_ids or bar.end<=pool.formed_at:
                continue
            hit=bar.high_ticks>=pool.price_ticks if pool.kind=='HIGH' else bar.low_ticks<=pool.price_ticks
            if hit:
                excluded.append((pool.id,'CONSUMED_OR_ORDERING_UNKNOWN',bar.id))
                return False
        return True
    recent = known_bars[-policy.near_atr_period:]
    atr = None
    if len(recent) == policy.near_atr_period:
        all_bars = known_bars
        values = []
        for idx, b in enumerate(recent, start=len(all_bars)-len(recent)):
            prev = all_bars[idx-1].close_ticks if idx else b.open_ticks
            values.append(max(b.high_ticks-b.low_ticks, abs(b.high_ticks-prev), abs(b.low_ticks-prev)))
        atr = Decimal(sum(values)) / len(values)
    near = policy.near_atr_fraction * atr if atr is not None else None
    versions = {}
    for r in ranges:
        if r.available_at <= at:
            versions[r.id] = r
    active = [r for r in versions.values() if (segment_start is None or getattr(r,'formed_at',r.available_at)>=segment_start) and r.status != 'BROKEN' and not r.details.get('endpoint_broken') and r.details.get('endpoint_stage') == 'CONFIRMED_DELIVERY' and r.direction == side
              and min(r.origin_ticks,r.endpoint_ticks) <= entry <= max(r.origin_ticks,r.endpoint_ticks)]
    selected_range = min(active,key=lambda r:(abs(r.endpoint_ticks-r.origin_ticks),r.id)) if active else None
    protected = []
    protection_linked = selected_range is not None and (selected_range.id in protection_range_ids or selected_range.details.get('seed_break_event_id') in protection_evidence_ids or getattr(selected_range,'protected_turn_id',None) in protection_evidence_ids)
    if selected_range and not protection_linked:
        excluded.append((selected_range.id,'NO_ENTRY_EPISODE_PROTECTION_LINK',selected_range.protected_liquidity_id))
    if protection_linked:
        pool = next((p for p in liquidity if p.id == selected_range.protected_liquidity_id and p.available_at <= at),None)
        if pool and standing(pool) and sign*(entry-pool.price_ticks)>0:
            protected.append((pool.id,pool.price_ticks,'active_range_protected_wick'))
    for b in protection_bars:
        if b.available_at <= at and (segment_start is None or b.start>=segment_start):
            p = b.low_ticks if side == 'BUY' else b.high_ticks
            if sign * (entry-p) > 0:
                protected.append((b.id, p, 'pattern_wick'))
    for obj in (*levels, *liquidity):
        if not current(obj) or sign*(entry-obj.price_ticks) <= 0:
            continue
        # Nearby same-TF objects may legitimately be swept before expansion.
        if obj.tf == tf and near is not None and abs(entry-obj.price_ticks) <= near and (not hasattr(obj,'form') or standing(obj)):
            protected.append((obj.id, obj.price_ticks, 'nearby_structure_or_liquidity_OUR_CHOICE'))
    pad = int(instrument.unit_ticks(policy.stop_buffer_units).to_integral_value(rounding=ROUND_CEILING))
    stop = None
    if policy.risk_profile in ('owner_fixed11', 'fixed11', 'fixed', 'fixed_pips'):
        distance = int(instrument.unit_ticks(policy.fixed_stop_units).to_integral_value(rounding=ROUND_CEILING))
        stop = entry-sign*distance
    elif policy.risk_profile in ('context_liquidity', 'source_structural', 'structural') and protected:
        boundary = min(p for _, p, _ in protected) if sign == 1 else max(p for _, p, _ in protected)
        stop = boundary-sign*max(pad, 1)
    elif policy.risk_profile == 'zone_edge' and zone_bounds is not None:
        low, high = zone_bounds
        if (type(low) is int and type(high) is int and low < high
                and low <= entry <= high):
            boundary = low if side == 'BUY' else high
            stop = boundary-sign*max(pad, 1)
    # Source stop prices cannot be reconstructed from position boxes or fixtures.
    target = None
    targets = []
    erl_kind = 'HIGH' if side == 'BUY' else 'LOW'
    for obj in liquidity:
        if selected_range is None or obj.id != selected_range.endpoint_liquidity_id or obj.tf != tf or obj.kind != erl_kind or obj.available_at > at or sign*(obj.price_ticks-entry) <= 0:
            continue
        if not standing(obj):
            continue
        targets.append((obj.price_ticks, obj.id, 'entry_tf_erl'))
    if policy.target_profile in ('nearest_erl', 'entry_erl'):
        if targets:
            target = min(targets, key=lambda x: (sign*(x[0]-entry), x[1]))[0]
        # Counterweekly/retracement trades stop at known nearer opposing KL.
        if (story.details.get('counterweekly_target_guard_required') or story.details.get('initial_weekly_relation') == 'COUNTER_WEEKLY' or story.details.get('retracement')):
            for lv in levels:
                if current(lv) and sign*(lv.price_ticks-entry) > 0:
                    role = role_lookup(lv, at) if role_lookup else lv.initial_role
                    if role in (('RESISTANCE','SELL') if sign == 1 else ('SUPPORT','BUY')):
                        if target is not None and sign*(lv.price_ticks-entry) < sign*(target-entry):
                            target = lv.price_ticks
    elif policy.target_profile in ('fixed3r', 'fixed_r') and stop is not None:
        target = entry+sign*3*abs(entry-stop)
    elif policy.target_profile == 'story_destination':
        dest = story.destination_ticks
        if dest is not None and sign*(dest-entry)>0:
            target = dest
    details = dict(protected_objects=protected, protection_shortfall=[oid for oid,p,_ in protected
        if stop is not None and sign*(p-stop)<0], story_destination_ticks=story.destination_ticks,
        story_destination_ref_id=story.destination_ref_id, target_candidates=targets,
        risk_profile=policy.risk_profile, target_profile=policy.target_profile,
        zone_bounds=zone_bounds, zone_edge_experiment=policy.risk_profile == 'zone_edge',
        zone_geometry_policy='fvg_wick3_v1_OUR_CHOICE' if zone_bounds is not None else None,
        numerical_conventions='OUR_CHOICE', protection_scope_policy='entry_episode_linked_v1', protection_evidence_ids=tuple(protection_evidence_ids), protection_range_ids=tuple(protection_range_ids), range_origin_protection_linked=protection_linked, excluded_objects=excluded, current_segment=segment, current_segment_start=segment_start, near_ticks=near, entry_range_id=selected_range.id if selected_range else None, entry_range_version=selected_range.version_id if selected_range else None)
    reasons=[]
    if stop is None: reasons.append('zone_geometry_unresolved' if policy.risk_profile == 'zone_edge' else 'risk_boundary_unresolved')
    if target is None: reasons.append('target_unresolved')
    if stop is not None and sign*(entry-stop)<=0: reasons.append('invalid_stop_geometry')
    if target is not None and sign*(target-entry)<=0: reasons.append('invalid_target_geometry')
    details['unresolved_reasons']=reasons
    return RiskResult(stop, target, 'UNRESOLVED' if reasons else 'ELIGIBLE', details)
