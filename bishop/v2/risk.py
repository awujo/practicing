"""Causal protection and target alternatives; all numerical defaults are OUR CHOICE."""
from dataclasses import dataclass
from decimal import ROUND_CEILING
from .types import Instrument, StrategyPolicy


@dataclass(frozen=True)
class RiskResult:
    stop_ticks: int | None
    target_ticks: int | None
    status: str
    details: dict


def plan(side, entry, at, tf, bars, levels, liquidity, story, instrument: Instrument,
         policy: StrategyPolicy, *, role_lookup=None, protection_bars=(), ranges=(), zone_bounds=None):
    sign = 1 if side == 'BUY' else -1
    known_bars = [b for b in bars if b.complete and b.available_at <= at]
    recent = known_bars[-policy.near_atr_period:]
    atr = None
    if len(recent) == policy.near_atr_period:
        all_bars = known_bars
        values = []
        for idx, b in enumerate(recent, start=len(all_bars)-len(recent)):
            prev = all_bars[idx-1].close_ticks if idx else b.open_ticks
            values.append(max(b.high_ticks-b.low_ticks, abs(b.high_ticks-prev), abs(b.low_ticks-prev)))
        atr = sum(values) / len(values)
    near = float(policy.near_atr_fraction) * atr if atr is not None else None
    versions = {}
    for r in ranges:
        if r.available_at <= at:
            versions[r.id] = r
    active = [r for r in versions.values() if r.status != 'BROKEN' and not r.details.get('endpoint_broken') and r.details.get('endpoint_stage') == 'CONFIRMED_DELIVERY' and r.direction == side
              and min(r.origin_ticks,r.endpoint_ticks) <= entry <= max(r.origin_ticks,r.endpoint_ticks)]
    selected_range = min(active,key=lambda r:(abs(r.endpoint_ticks-r.origin_ticks),r.id)) if active else None
    protected = []
    if selected_range:
        pool = next((p for p in liquidity if p.id == selected_range.protected_liquidity_id and p.available_at <= at),None)
        if pool:
            protected.append((pool.id,pool.price_ticks,'active_range_protected_wick'))
    for b in protection_bars:
        if b.available_at <= at:
            p = b.low_ticks if side == 'BUY' else b.high_ticks
            if sign * (entry-p) > 0:
                protected.append((b.id, p, 'pattern_wick'))
    for obj in (*levels, *liquidity):
        if obj.available_at > at or sign*(entry-obj.price_ticks) <= 0:
            continue
        # Nearby same-TF objects may legitimately be swept before expansion.
        if obj.tf == tf and near is not None and abs(entry-obj.price_ticks) <= near:
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
        # Do not target pools already touched before placement.
        if any(b.start >= obj.available_at and b.available_at <= at and
               (b.high_ticks >= obj.price_ticks if sign == 1 else b.low_ticks <= obj.price_ticks)
               for b in known_bars):
            continue
        targets.append((obj.price_ticks, obj.id, 'entry_tf_erl'))
    if policy.target_profile in ('nearest_erl', 'entry_erl'):
        if targets:
            target = min(targets, key=lambda x: (sign*(x[0]-entry), x[1]))[0]
        # Counterweekly/retracement trades stop at known nearer opposing KL.
        if (story.details.get('counterweekly_target_guard_required') or story.details.get('initial_weekly_relation') == 'COUNTER_WEEKLY' or story.details.get('retracement')):
            for lv in levels:
                if lv.available_at <= at and sign*(lv.price_ticks-entry) > 0:
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
        numerical_conventions='OUR_CHOICE', near_ticks=near, entry_range_id=selected_range.id if selected_range else None, entry_range_version=selected_range.version_id if selected_range else None)
    reasons=[]
    if stop is None: reasons.append('zone_geometry_unresolved' if policy.risk_profile == 'zone_edge' else 'risk_boundary_unresolved')
    if target is None: reasons.append('target_unresolved')
    details['unresolved_reasons']=reasons
    return RiskResult(stop, target, 'UNRESOLVED' if reasons else 'ELIGIBLE', details)
