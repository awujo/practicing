"""Named, causal entry alternatives. Numerical geometry is OUR CHOICE.

All candidates retain their family. Missing protection/ERL remains unresolved;
no fixture, later performance or expected future sweep controls eligibility.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from .types import Clock, Event, Setup, Liquidity, stable_id, utc
from .risk import plan

BREAKS = frozenset(('BREAKOUT', 'BOS', 'SWEEP_BOS', 'EXTERNAL_BREAK'))
FAMILIES = ('direct_h4', 'direct_h2', 'confirmation_bo', 'confirmation_sweep_bos',
            'confirmation_engulfed_oc', 'confirmation_standing_extreme',
            'engulf_av_retest', 'oc_break_retest', 'engulf_irl_retest',
            'aggressive_kl_imbalance', 'nested_confirmation')


@dataclass(frozen=True)
class Imbalance:
    id: str
    instrument: str
    tf: str
    low_ticks: int
    high_ticks: int
    side: str
    available_at: object
    bar_ids: tuple[str, ...]
    policy_id: str


@dataclass(frozen=True)
class EntryResult:
    setups: tuple[Setup, ...]
    events: tuple[Event, ...]
    support: tuple[dict, ...]
    imbalances: tuple[Imbalance, ...]


def _role(level, structure, at):
    from .structure import role_at
    return role_at(level, structure.events, at)


def _direction_role(side):
    return 'SUPPORT' if side == 'BUY' else 'RESISTANCE'


def _imbalance(bars, policy):
    out=[]
    for i in range(2, len(bars)):
        a, m, b=bars[i-2:i+1]
        if len({a.segment_id,m.segment_id,b.segment_id}) != 1:
            continue
        if a.high_ticks < b.low_ticks:
            lo,hi,side=a.high_ticks,b.low_ticks,'BUY'
        elif b.high_ticks < a.low_ticks:
            lo,hi,side=b.high_ticks,a.low_ticks,'SELL'
        else:
            continue
        out.append(Imbalance(stable_id('fvg',a.id,m.id,b.id,policy.id),b.instrument,b.tf,
                             lo,hi,side,max(x.available_at for x in (a,m,b)),
                             (a.id,m.id,b.id),policy.id))
    return out


def _atr(bars, at, policy):
    known=[b for b in bars if b.available_at <= at]
    if len(known)<policy.near_atr_period:
        return None
    values=[]
    for i in range(len(known)-policy.near_atr_period,len(known)):
        b=known[i]; p=known[i-1].close_ticks if i else b.open_ticks
        values.append(max(b.high_ticks-b.low_ticks,abs(b.high_ticks-p),abs(b.low_ticks-p)))
    return sum(values)/len(values)*float(policy.near_atr_fraction)


def _engulfs(a,b,side):
    if a.segment_id != b.segment_id or a.side == side or a.side is None or b.side != side:
        return False
    return (min(b.open_ticks,b.close_ticks)<=min(a.open_ticks,a.close_ticks)
            and max(b.open_ticks,b.close_ticks)>=max(a.open_ticks,a.close_ticks)
            and (b.close_ticks>a.open_ticks if side=='BUY' else b.close_ticks<a.open_ticks))


def _is_active(story, at, story_events):
    for event in story_events:
        if event.available_at>at:
            continue
        if (event.reference_id==story.id or event.details.get('story_id')==story.id):
            if event.kind in ('STORY_SUSPENDED','STORY_RETIRED','STORY_INVALIDATED','STORY_FLIPPED','DESTINATION_REACHED','STORY_DESTINATION_REACHED'):
                return False
    return True


def _pool_taken_before(pool, reaction_bar, bars):
    """A previously witnessed take cannot manufacture another fresh reaction.

    Check only observations available before this reaction starts. This does
    not veto a live anticipatory order from a future sweep or touch.
    """
    return any(x.start >= pool.available_at and x.end <= reaction_bar.start
               and x.available_at <= reaction_bar.start
               and (x.high_ticks > pool.price_ticks if pool.kind == 'HIGH'
                    else x.low_ticks < pool.price_ticks) for x in bars)


def _reaction_episode_reason(reaction, candidate_bar, h4_events):
    """Retire entry pairing, never the higher story or a previously placed order.

    Scope/role loss and a fresh same-scope context break are causal boundaries;
    elapsed bar counts and distance are deliberately absent.
    """
    rb, level, parent_break, _ = reaction
    if rb.segment_id != candidate_bar.segment_id:
        return 'reaction_data_segment_changed'
    opposite = 'SELL' if parent_break.side == 'BUY' else 'BUY'
    for event in h4_events:
        if event.available_at <= rb.available_at:
            continue
        if (event.available_at <= candidate_bar.available_at
                and event.kind == 'LEVEL_ROLE_CHANGE'
                and event.reference_id == level.id and event.side == opposite):
            return 'reaction_H4_level_role_lost'
        same_scope = parent_break.scope_id is not None and event.scope_id == parent_break.scope_id
        if not same_scope:
            continue
        if event.available_at <= candidate_bar.available_at and event.kind == 'RANGE_BROKEN':
            return 'reaction_H4_scope_broken'
        # Simultaneous parent/child confirmation is not a later episode.
        # A new context already known before the child starts needs its own
        # liquidity/reaction chain before it can sponsor another CE.
        if (event.available_at <= candidate_bar.start and event.kind in BREAKS
                and event.side == parent_break.side and event.evidence_status == 'KNOWN'):
            return 'reaction_replaced_by_fresh_H4_break'
    return None


def _first_take_for_reaction(pool, reaction_bar, bars, level, parent_break, h4_events):
    """Carry the first take forward within its original, still-valid episode.

    A later KL rejection need not repeat the sweep. Conversely, a subsequent
    take cannot replace a first take belonging to an older or broken episode.
    Only closed observations known by the reaction are considered.
    """
    first = next((b for b in bars
        if b.start >= pool.available_at and b.end <= reaction_bar.end
        and b.available_at <= reaction_bar.available_at
        and (b.high_ticks > pool.price_ticks if pool.kind == 'HIGH'
             else b.low_ticks < pool.price_ticks)), None)
    if first is None or first.start < max(parent_break.available_at, level.available_at):
        return None
    opposite='SELL' if parent_break.side=='BUY' else 'BUY'
    for event in h4_events:
        if not parent_break.available_at < event.available_at <= reaction_bar.available_at:
            continue
        if event.reference_id==level.id and (event.kind=='LEVEL_UNAVAILABLE' or
                (event.kind=='LEVEL_ROLE_CHANGE' and event.side==opposite)):
            return None
        if (parent_break.scope_id is not None and event.scope_id==parent_break.scope_id
                and event.kind=='RANGE_BROKEN'):
            return None
    if _reaction_episode_reason((first, level, parent_break, (pool,)), reaction_bar, h4_events):
        return None
    return first


def detect_setups(bars_by_tf, structures, stories, instrument, policy, *, story_events=(), eligibility_start=None):
    if eligibility_start is not None:
        eligibility_start=utc(eligibility_start)
    from .structure import RoleIndex
    role_indices={tf:RoleIndex(result.events) for tf,result in structures.items()}
    # Only actual current-entry-TF event lineage can sponsor range protection.
    # A containing price range or a higher-TF context event is not such a link.
    event_scope_index={tf:{e.id:(e.scope_id,e.available_at) for e in result.events}
                       for tf,result in structures.items()}
    role_cache={}
    def cached_role(level, result, at):
        key=(level.id,at)
        if key not in role_cache:
            role_cache[key]=role_indices[level.tf].role_at(level,at)
        return role_cache[key]
    stories=getattr(stories,'stories',stories)
    bars_by_tf={tf:tuple(sorted((b for b in bs if b.complete),key=lambda b:b.start))
                for tf,bs in bars_by_tf.items()}
    segment_starts={}
    for tf, bars in bars_by_tf.items():
        segment_starts[tf]={}
        for bar in bars:
            segment_starts[tf].setdefault(bar.segment_id,bar.start)
    imbalances=tuple(g for tf in policy.entry_tfs for g in _imbalance(bars_by_tf.get(tf,()),policy))
    setups={}; events={}; support=[]
    reaction_takes={}
    take_link_cache={}
    take_events={}
    def linked_takes(hp, rb, bs, level, parent, h4):
        linked=[]
        for pool in hp:
            key=(pool.id,rb.id,level.id,parent.id)
            if key not in take_link_cache:
                take_link_cache[key]=_first_take_for_reaction(pool,rb,bs,level,parent,h4.events)
            first=take_link_cache[key]
            if first is None: continue
            take=take_events[(pool.id,first.tf)]
            linked.append((pool,take))
        reaction_takes[(rb.id,level.id,parent.id)]=tuple(t.id for _,t in linked)
        return tuple(p for p,_ in linked)
    profile=policy.source_profile
    # Profiles select procedures before outcomes. source_all is the audit view.
    if profile in ('source_all','all_routes'):
        enabled=set(FAMILIES)
    elif profile in ('owner_aggressive','aggressive_direct','plug_and_play'):
        enabled={'direct_h4','direct_h2','aggressive_kl_imbalance'}
    elif profile == 'nested_confirmation':
        enabled={'nested_confirmation'}
    elif profile == 'core_course':
        enabled={'engulf_av_retest','oc_break_retest','engulf_irl_retest'}
    else:
        enabled=set(FAMILIES)-{'direct_h4','direct_h2','aggressive_kl_imbalance','nested_confirmation'}
    formed_pools=[]
    # Explicit plug single/series IRL alternatives, known only at candle close.
    for tf,result in structures.items():
        bs=bars_by_tf.get(tf,())
        for br in result.events:
            if br.kind not in BREAKS or br.side is None: continue
            origin=next((b for b in bs if b.id in br.bar_ids),None)
            if origin is None: continue
            following=[b for b in bs if b.start>=origin.end and b.segment_id==origin.segment_id]
            series=[]
            for b in following:
                contained=b.low_ticks>=origin.low_ticks and b.high_ticks<=origin.high_ticks
                external_sweep=(b.high_ticks>origin.high_ticks and b.close_ticks<=origin.high_ticks) if br.side=='BUY' else (b.low_ticks<origin.low_ticks and b.close_ticks>=origin.low_ticks)
                if not contained and not external_sweep: break
                series.append(b)
                price=min(x.low_ticks for x in series) if br.side=='BUY' else max(x.high_ticks for x in series)
                ids=tuple(x.id for x in series)
                formed_pools.append(Liquidity(id=stable_id('entry_irl',br.id,ids,policy.id),instrument=origin.instrument,
                    tf=tf,kind='LOW' if br.side=='BUY' else 'HIGH',price_ticks=price,
                    formed_at=b.end,available_at=max(br.available_at,*[z.available_at for z in series]),form='BAR' if len(series)==1 else 'SERIES',
                    bar_ids=ids,policy_id=policy.id,details={'role':'IRL','breakout_id':br.id,'convention':'OUR_CHOICE_containment_inclusive_v1'}))
                if external_sweep: break
    all_liq=tuple(l for r in structures.values() for l in r.liquidity)+tuple(formed_pools)
    all_levels=tuple(l for r in structures.values() for l in r.levels)
    # Publish observed takes independently of whether a later reaction exists.
    # Otherwise adding that later reaction would backdate a new event into an
    # earlier report. One immutable event is shared by related reactions.
    for tf in dict.fromkeys((*policy.entry_tfs,'H1') if 'nested_confirmation' in enabled else policy.entry_tfs):
        for pool in all_liq:
            if pool.tf!='H4': continue
            first=next((b for b in bars_by_tf.get(tf,()) if b.start>=pool.available_at
                and (b.high_ticks>pool.price_ticks if pool.kind=='HIGH' else b.low_ticks<pool.price_ticks)),None)
            if first is None: continue
            take=Event(id=stable_id('entry_first_take',pool.id,first.id,policy.id),
                kind='LIQUIDITY_FIRST_TAKEN',instrument=first.instrument,tf=first.tf,
                clock=Clock(first.start,first.end,max(pool.available_at,first.available_at)),
                side='SELL' if pool.kind=='HIGH' else 'BUY',
                reference_id=pool.id,price_ticks=pool.price_ticks,bar_ids=(first.id,),
                evidence_ids=(pool.id,),policy_id=policy.id,
                details={'link_policy':'first_take_then_same_episode_reaction_v1'})
            events[take.id]=take
            take_events[(pool.id,tf)]=take
    for tf in policy.entry_tfs:
        support.append(dict(tf=tf,route='entries',status='SUPPORTED' if tf in structures and tf in bars_by_tf else 'UNSUPPORTED',
                            families=FAMILIES, enabled_families=tuple(f for f in FAMILIES if f in enabled),
                            numerical_conventions='OUR_CHOICE'))
    support.append(dict(route='optional_nested_confirmation',status='SUPPORTED',enabled='nested_confirmation' in enabled,reason='declared_H1_break_reaction_standing_then_lower_engulf_chain_OUR_CHOICE'))
    support.append(dict(route='pdf_p8_standing_extreme',status='UNRESOLVED',
                        reason='high_swept_low_standing_LONG_reference_pair_unresolved'))

    def emit(model,story,tf,level,at,causes,protection,liq=(),phase='origin',extra=None,zone_bounds=None):
        if eligibility_start is not None and at < eligibility_start:
            return
        if model not in enabled or story.available_at>at or not _is_active(story,at,story_events):
            return
        result=structures[tf]
        if cached_role(level,result,at) not in (_direction_role(story.side),story.side):
            return
        if story.details.get('owner_selection') == 'BLOCKED_COUNTERWEEKLY' or (not policy.allow_counterweekly and story.details.get('initial_weekly_relation') == 'COUNTER_WEEKLY'):
            return
        protection_evidence=tuple(dict.fromkeys((*causes,level.id)))
        scope_index=event_scope_index[tf]
        protection_scopes=tuple(dict.fromkeys(scope_index[cause][0] for cause in causes
            if cause in scope_index and scope_index[cause][0] is not None
            and scope_index[cause][1]<=at))
        risk=plan(story.side,level.price_ticks,at,tf,bars_by_tf[tf],all_levels,all_liq,
                  story,instrument,policy,role_lookup=lambda l,t:cached_role(l,structures[l.tf],t),
                  protection_bars=protection,ranges=result.ranges,zone_bounds=zone_bounds,
                  protection_evidence_ids=protection_evidence,protection_range_ids=protection_scopes)
        sid=stable_id('setup',story.id,tf,model,level.id,tuple(causes),policy.id)
        clock=Clock(at,at,at)
        details=dict(risk.details,phase=phase,source_profile=profile,model_enabled=True,
                     causal_selection='first_eligible_then_higher_tf_same_batch_OUR_CHOICE',
                     expected_sweep_is_not_fill_veto=True,**(extra or {}))
        expiry=at+timedelta(minutes=policy.pending_minutes) if policy.pending_minutes else None
        setup=Setup(id=sid,instrument=instrument.symbol,tf=tf,model=model,side=story.side,
            story_id=story.id,clock=clock,entry_ticks=level.price_ticks,stop_ticks=risk.stop_ticks,
            target_ticks=risk.target_ticks,risk_profile=policy.risk_profile,status=risk.status,
            level_id=level.id,liquidity_ids=tuple(l.id for l in liq),
            evidence_ids=tuple(dict.fromkeys((story.id,level.id,*causes))),expires_at=expiry,details=details)
        setups[sid]=setup
        kind='ENTRY_ELIGIBLE' if setup.status=='ELIGIBLE' else 'ENTRY_UNRESOLVED'
        e=Event(id=stable_id(kind,sid),kind=kind,instrument=instrument.symbol,tf=tf,clock=clock,
                side=story.side,reference_id=sid,price_ticks=level.price_ticks,
                evidence_ids=setup.evidence_ids,policy_id=policy.id,evidence_status='KNOWN' if risk.status=='ELIGIBLE' else 'UNRESOLVED',
                details={'model':model,'reasons':risk.details['unresolved_reasons']})
        events[e.id]=e

    def select_level(tf,side,at,reference,*,kind=None,formed_after=None):
        result=structures[tf]
        levels=[l for l in result.levels if l.available_at<=at and (kind is None or l.kind==kind)
                and (formed_after is None or l.formed_at>=formed_after)
                and cached_role(l,result,at) in (_direction_role(side),side)]
        # Nearest same-TF relevant level, never chosen by which later retests.
        levels=[l for l in levels if (l.price_ticks<=reference if side=='BUY' else l.price_ticks>=reference)]
        return min(levels,key=lambda l:(abs(reference-l.price_ticks),-l.available_at.timestamp(),l.id)) if levels else None

    def pools(tf,side,at,after):
        known=[b for b in bars_by_tf[tf] if b.available_at<=at]
        segment_start=segment_starts[tf][known[-1].segment_id] if known else at
        return tuple(l for l in all_liq if l.tf==tf and l.formed_at>=segment_start and l.available_at>=segment_start and (l.form not in ('BAR','PRIOR_PERIOD','SESSION') or l.details.get('role')=='IRL') and l.available_at<=at and l.formed_at>=after
                     and l.kind==('LOW' if side=='BUY' else 'HIGH'))

    for story in stories:
        if story.details.get('owner_selection') == 'BLOCKED_COUNTERWEEKLY':
            support.append(dict(route='owner_selection',story_id=story.id,status='BLOCKED_COUNTERWEEKLY'))
        for tf in policy.entry_tfs:
            if tf not in structures or tf not in bars_by_tf:
                continue
            bs=bars_by_tf[tf]; result=structures[tf]
            h4=structures.get('H4')
            h4breaks=[e for e in (h4.events if h4 else ()) if e.kind in BREAKS and e.side==story.side
                         and e.available_at>=story.clock.occurred_from and e.evidence_status=='KNOWN']
            # Direct readiness: known liquidity, no future sweep/reaction gate.
            if tf in ('H4','H2'):
                breaks=[e for e in result.events if e.kind in BREAKS and e.side==story.side
                        and e.available_at>=story.clock.occurred_from and e.evidence_status=='KNOWN']
                for br in breaks:
                    parents=[br] if tf=='H4' else []
                    if tf=='H2':
                        # Own H2 structure must occur in the H4 breakout candle,
                        # or in its subsequent episode before a newer H4 BO.
                        enclosing=[]; preceding=[]
                        for p in h4breaks:
                            pb=next((z for z in bars_by_tf.get('H4',()) if z.id in p.bar_ids),None)
                            if pb is not None and pb.start<=br.clock.occurred_from and br.clock.occurred_to<=pb.end:
                                enclosing.append(p)
                            elif p.available_at<=br.clock.occurred_from:
                                preceding.append(p)
                        parents=enclosing or ([max(preceding,key=lambda p:(p.available_at,p.id))] if preceding else [])
                    if not parents:
                        continue
                    parent=min(parents,key=lambda p:(max(p.available_at,br.available_at),p.id))
                    for pool in pools(tf,story.side,max([b.available_at for b in bs],default=br.available_at),br.clock.occurred_from):
                        at=max(story.available_at,parent.available_at,br.available_at,pool.available_at)
                        known=[b for b in bs if b.available_at<=at]
                        if not known: continue
                        segment_start=segment_starts[tf][known[-1].segment_id]
                        break_bars=[x for x in bs if x.id in br.bar_ids]
                        if (br.clock.occurred_from<segment_start or pool.formed_at<segment_start
                                or not break_bars or break_bars[-1].segment_id!=known[-1].segment_id): continue
                        if tf=='H2':
                            parent_bars=[x for x in bars_by_tf.get('H4',()) if x.id in parent.bar_ids]
                            if not parent_bars or parent_bars[-1].end<=segment_start: continue
                        lv=select_level(tf,story.side,at,known[-1].close_ticks)
                        if lv:
                            pb=[b for b in known if b.id in pool.bar_ids or b.id in br.bar_ids]
                            emit('direct_h4' if tf=='H4' else 'direct_h2',story,tf,lv,at,(br.id,parent.id,pool.id),pb,(pool,),
                                 phase='continuation' if br.available_at>story.available_at else 'origin',
                                 extra={'h4_breakout_closed_at':parent.available_at.isoformat()})
            # Reaction context: observe H4 KL contact in closed lower bars,
            # so no containing-H4-close is invented from lower-TF data.
            reactions=[]
            if h4 and tf!='H4':
                for b in bs:
                    if b.available_at<story.available_at: continue
                    for lv4 in h4.levels:
                        if lv4.available_at>b.start or cached_role(lv4,h4,b.start) not in (_direction_role(story.side),story.side): continue
                        if not b.low_ticks<=lv4.price_ticks<=b.high_ticks: continue
                        if not (b.close_ticks>lv4.price_ticks if story.side=='BUY' else b.close_ticks<lv4.price_ticks): continue
                        segment_start=segment_starts[tf][b.segment_id]
                        related=[e for e in h4breaks if e.available_at<=b.start and e.clock.occurred_from>=segment_start]
                        if not related: continue
                        br=max(related,key=lambda e:e.available_at)
                        hp=pools('H4',story.side,b.start,br.clock.occurred_from)
                        if not hp and profile not in ('source_all','all_routes','core_course'): continue
                        # Bishop confirmation waits for known H4 liquidity taken.
                        swept=linked_takes(hp,b,bs,lv4,br,h4)
                        if not swept and profile not in ('source_all','all_routes','core_course'): continue
                        reactions.append((b,lv4,br,tuple(swept)))
            retired_reactions=set()
            def reaction_for(b):
                valid=[r for r in reactions if r[0].end<=b.start and r[0].available_at<=b.available_at]
                if not valid: return None
                # Do not fall back to an even older reaction after the current
                # episode loses its support. A new witnessed reaction replaces it.
                current=max(valid,key=lambda r:(r[0].end,r[0].available_at,r[1].id))
                reason=_reaction_episode_reason(current,b,h4.events)
                if reason:
                    key=(current[0].id,current[1].id,reason)
                    if key not in retired_reactions:
                        support.append(dict(route='entry_reaction_episode',story_id=story.id,
                            tf=tf,status='RETIRED',reason=reason,
                            reaction_bar_id=current[0].id,level_id=current[1].id,
                            parent_break_id=current[2].id,observed_at=b.available_at.isoformat()))
                        retired_reactions.add(key)
                    return None
                return current
            for i,b in enumerate(bs):
                if b.available_at<story.available_at: continue
                reaction=reaction_for(b)
                if reaction:
                    rb,lv4,hbr,hp=reaction
                    causes=(rb.id,lv4.id,hbr.id,*[p.id for p in hp],
                            *reaction_takes.get((rb.id,lv4.id,hbr.id),()))
                    at=max(story.available_at,b.available_at,rb.available_at,bs[i-1].available_at if i else b.available_at,lv4.available_at,hbr.available_at,*[p.available_at for p in hp])
                    for br in result.events:
                        if not hp: continue
                        if br.kind not in BREAKS or br.side!=story.side or br.available_at!=b.available_at: continue
                        if br.clock.occurred_to<rb.end: continue
                        lv=select_level(tf,story.side,at,b.close_ticks)
                        if lv:
                            model='confirmation_sweep_bos' if br.kind=='SWEEP_BOS' else 'confirmation_bo'
                            emit(model,story,tf,lv,at,(*causes,br.id),(rb,b),hp)
                    # Session OC disrespect permits variable engulf body placement.
                    for lv in result.levels:
                        if lv.kind!='OC' or lv.available_at>b.start or lv.side==story.side: continue
                        if not (b.open_ticks<=lv.price_ticks<b.close_ticks if story.side=='BUY' else b.close_ticks<lv.price_ticks<=b.open_ticks): continue
                        if hp:
                            emit('confirmation_engulfed_oc',story,tf,lv,at,(*causes,b.id),(rb,b),hp)
                        if i and _engulfs(bs[i-1],b,story.side):
                            emit('oc_break_retest',story,tf,lv,at,(*causes,b.id),(rb,bs[i-1],b),hp)
                    if i and bs[i-1].segment_id==b.segment_id:
                        a=bs[i-1]
                        standing=(b.low_ticks<a.low_ticks and b.high_ticks<a.high_ticks and b.close_ticks>a.low_ticks) if story.side=='BUY' else (b.high_ticks>a.high_ticks and b.low_ticks>a.low_ticks and b.close_ticks<a.high_ticks)
                        if standing and hp:
                            lv=select_level(tf,story.side,at,b.close_ticks,kind='V' if story.side=='BUY' else 'A',formed_after=a.start)
                            if lv:
                                emit('confirmation_standing_extreme',story,tf,lv,at,(*causes,a.id,b.id),(rb,a,b),hp,
                                     extra={'geometry':'restricted_adjacent_E5_OUR_CHOICE','reference_bar_id':a.id,
                                            'standing_through':b.end.isoformat(),'pdf_p8_mapping':'UNRESOLVED'})
                    if i and _engulfs(bs[i-1],b,story.side):
                        lv=select_level(tf,story.side,at,b.close_ticks,kind='V' if story.side=='BUY' else 'A',formed_after=bs[i-1].start)
                        if lv:
                            emit('engulf_av_retest',story,tf,lv,max(at,lv.available_at),(*causes,b.id),(rb,bs[i-1],b),hp)
                        # A/V may become available with following bar; never use it early.
                        if i+1<len(bs):
                            n=bs[i+1]
                            nat=max(n.available_at,b.available_at,bs[i-1].available_at,story.available_at,at)
                            lv=select_level(tf,story.side,nat,b.close_ticks,kind='V' if story.side=='BUY' else 'A',formed_after=bs[i-1].start)
                            near=_atr(bs,b.start,policy)
                            if lv and n.segment_id==b.segment_id and near is not None:
                                d=n.low_ticks-lv.price_ticks if story.side=='BUY' else lv.price_ticks-n.high_ticks
                                approach=n.low_ticks<b.low_ticks if story.side=='BUY' else n.high_ticks>b.high_ticks
                                if 0<d<=near and approach:
                                    emit('engulf_irl_retest',story,tf,lv,nat,(*causes,b.id,n.id),(rb,b,n),hp,
                                         extra={'inducement_bar_id':n.id,'near_ticks':near,'future_sweep_required_for_fill':False})
                # Aggressive overlap route does not require new inducement.
                for gap in imbalances:
                    if gap.tf!=tf or gap.side!=story.side or gap.available_at>b.available_at: continue
                    # Evaluate once at gap availability or story readiness.
                    at=max(story.available_at,gap.available_at)
                    if b.available_at!=at: continue
                    for lv in result.levels:
                        if lv.available_at>at or not gap.low_ticks<=lv.price_ticks<=gap.high_ticks: continue
                        if any(x.start>=gap.available_at and x.available_at<=at and
                               (x.low_ticks<=gap.low_ticks if story.side=='BUY' else x.high_ticks>=gap.high_ticks) for x in bs): continue
                        emit('aggressive_kl_imbalance',story,tf,lv,at,(gap.id,), (b,),phase='continuation',
                             extra={'imbalance_id':gap.id,'imbalance_policy':'fvg_wick3_v1_OUR_CHOICE'},zone_bounds=(gap.low_ticks,gap.high_ticks))
    # Optional T3-style nested chain: H4 reaction -> H1 BO -> H1 KL
    # reaction -> H1 standing-extreme -> lower engulf/KL. Every link is explicit;
    # a lone lower engulf cannot masquerade as the entire chain.
    if 'nested_confirmation' in enabled:
        h1=structures.get('H1'); h4=structures.get('H4')
        if h1 is None or h4 is None:
            support.append(dict(route='nested_confirmation',status='UNRESOLVED',reason='missing_H1_H4_lineage'))
        else:
            h1bars=bars_by_tf.get('H1',())
            for story in stories:
                h4bos=[e for e in h4.events if e.kind in BREAKS and e.side==story.side
                       and e.evidence_status=='KNOWN' and e.available_at>=story.clock.occurred_from]
                for br in h1.events:
                    if br.kind not in BREAKS or br.side!=story.side or br.evidence_status!='KNOWN': continue
                    if br.available_at<story.available_at: continue
                    # A preceding, positively witnessed H4 KL reaction and taken IRL.
                    witnessed=[]
                    for rb in h1bars:
                        if rb.available_at>br.clock.occurred_from or rb.available_at<story.available_at: continue
                        segment_start=segment_starts['H1'][rb.segment_id]
                        prior=[hb for hb in h4bos if hb.available_at<=rb.start and hb.clock.occurred_from>=segment_start]
                        if not prior: continue
                        hb=max(prior,key=lambda x:x.available_at)
                        hp=pools('H4',story.side,rb.start,hb.clock.occurred_from)
                        for level in h4.levels:
                            if level.available_at>rb.start or cached_role(level,h4,rb.start)!=story.side: continue
                            if rb.low_ticks<=level.price_ticks<=rb.high_ticks and (rb.close_ticks>level.price_ticks if story.side=='BUY' else rb.close_ticks<level.price_ticks):
                                swept=linked_takes(hp,rb,h1bars,level,hb,h4)
                                if not swept: continue
                                witnessed.append((rb,level,hb,swept))
                    if not witnessed: continue
                    rb,htflevel,hb,hp=max(witnessed,key=lambda x:x[0].available_at)
                    for i in range(1,len(h1bars)):
                        a,b=h1bars[i-1:i+1]
                        if a.start<br.available_at or a.segment_id!=b.segment_id: continue
                        if _reaction_episode_reason((rb,htflevel,hb,hp),b,h4.events): continue
                        standing=(b.low_ticks<a.low_ticks and b.high_ticks<a.high_ticks and b.close_ticks>a.low_ticks) if story.side=='BUY' else (b.high_ticks>a.high_ticks and b.low_ticks>a.low_ticks and b.close_ticks<a.high_ticks)
                        if not standing: continue
                        lv=select_level('H1',story.side,a.start,a.close_ticks)
                        if lv is None or not (a.low_ticks<=lv.price_ticks<=a.high_ticks): continue
                        if not (a.close_ticks>lv.price_ticks if story.side=='BUY' else a.close_ticks<lv.price_ticks): continue
                        for tf in ('M30','M15','M5'):
                            if tf not in policy.entry_tfs or tf not in structures: continue
                            lower=bars_by_tf.get(tf,())
                            for j in range(1,len(lower)):
                                x,y=lower[j-1:j+1]
                                if y.start<b.end or not _engulfs(x,y,story.side): continue
                                # No arbitrary later engulf: must still react at the
                                # nested H1 KL, with no intervening close-through.
                                if not (x.low_ticks<=lv.price_ticks<=x.high_ticks or y.low_ticks<=lv.price_ticks<=y.high_ticks): continue
                                if any(z.start>=b.end and z.end<y.start and
                                       (z.close_ticks<lv.price_ticks if story.side=='BUY' else z.close_ticks>lv.price_ticks)
                                       for z in lower): continue
                                at=max(story.available_at,hb.available_at,rb.available_at,htflevel.available_at,br.available_at,lv.available_at,a.available_at,b.available_at,x.available_at,y.available_at,*[p.available_at for p in hp])
                                child=select_level(tf,story.side,at,y.close_ticks,kind='V' if story.side=='BUY' else 'A',formed_after=x.start)
                                if child is None:
                                    support.append(dict(route='nested_confirmation',story_id=story.id,tf=tf,status='UNRESOLVED',reason='lower_AV_not_yet_available',evidence_ids=(br.id,a.id,b.id,x.id,y.id)))
                                    continue
                                chain=(hb.id,rb.id,htflevel.id,br.id,lv.id,a.id,b.id,x.id,y.id,
                                       *reaction_takes.get((rb.id,htflevel.id,hb.id),()))
                                emit('nested_confirmation',story,tf,child,at,chain,(rb,a,b,x,y),hp,
                                     extra={'nesting_chain_ids':chain,'parent_entry_tf':'H1',
                                            'standing_reference_bar_id':a.id,'standing_confirmation_bar_id':b.id,
                                            'lineage_policy':'T3_explicit_chain_OUR_CHOICE'})
    support.append(dict(route='entry_liquidity_forms',status='SUPPORTED',objects=tuple(formed_pools),forms=('BAR','SERIES','STRUCTURAL')))
    return EntryResult(tuple(sorted(setups.values(),key=lambda s:(s.available_at,s.id))),
                       tuple(sorted(events.values(),key=lambda e:(e.available_at,e.id))),tuple(support),imbalances)
