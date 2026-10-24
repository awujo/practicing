"""Offline orchestration. Source alternatives are never called a portfolio."""
from collections import Counter
from dataclasses import replace
from datetime import timedelta
from collections.abc import Mapping
from .types import StrategyPolicy, Order, jsonable, stable_id, utc
from .feed import load_feed
from .aggregation import aggregate, minutes, expected_slots, is_open
from .structure import analyze
from .impulse import assess
from .continuity import gaps_from_base, invalidate_levels, suspend_stories
from .sessions import collect_sessions
from .stories import find_stories
from .entries import detect_setups
from .simulation import simulate, Costs


def run(feed_or_path, manifest=None, *, as_of, history_start=None,
        scan_start=None, policy=None, costs=None, max_open_orders=10,
        include_diagnostics=False, management_actions=()):
    """Compute a frozen local run; never fetch data, dispatch, or trade.

    Costs must be supplied explicitly, including an explicit zero-cost hypothesis.
    source_all simulates independent alternatives, with no portfolio claim.
    """
    management_actions=tuple(dict(a) for a in management_actions)
    clock=utc(as_of)
    policy=StrategyPolicy(**policy) if isinstance(policy,dict) else policy or StrategyPolicy()
    if not isinstance(policy,StrategyPolicy): raise ValueError('StrategyPolicy required')
    if costs is None: raise ValueError('explicit execution costs required')
    costs=Costs(**costs) if isinstance(costs,dict) else costs
    if not isinstance(costs,Costs): raise ValueError('Costs required')
    if type(max_open_orders) is not int or max_open_orders<1: raise ValueError('positive integer max_open_orders required')
    feed=dict(feed_or_path) if isinstance(feed_or_path,Mapping) else load_feed(feed_or_path,manifest,clock,history_start)
    inst=feed['instrument']; base=tuple(feed['bars'])
    if any(b.available_at>clock for b in base): raise ValueError('feed contains future bars')
    if any(a.start>=b.start for a,b in zip(base,base[1:])): raise ValueError('feed must be ordered unique')
    # Snapshot rebuilding cannot preserve earlier gap/structure decisions when
    # an older candle first arrives after a newer one. Require receipt-order
    # replay before supporting such feeds; never silently rewrite history.
    if any(a.available_at>b.available_at for a,b in zip(base,base[1:])):
        raise ValueError('nonmonotone bar publication requires receipt-order replay; late internal bars unsupported')
    if any(b.instrument!=inst.symbol for b in base): raise ValueError('feed instrument mismatch')
    lower=utc(scan_start) if scan_start else None
    if lower and lower>clock: raise ValueError('scan_start after as_of')
    calendar=feed.get('manifest',{}).get('calendar',inst.calendar_id)
    # Mapping inputs are a typed local adapter, not a validation escape hatch.
    if base:
        base_tf=base[0].tf; duration=minutes(base_tf)
        if duration is None or duration<1: raise ValueError('intraday base feed required')
        segmented=[]; segment=0; previous=None
        for bar in base:
            if bar.tf!=base_tf or bar.end-bar.start!=timedelta(minutes=duration):
                raise ValueError('mixed timeframe or incorrect base duration')
            if (bar.start.timestamp()/60)%duration or not bar.complete:
                raise ValueError('complete duration-aligned base bars required')
            if not is_open(bar.start,calendar): raise ValueError('input outside declared calendar')
            if previous is not None:
                if bar.start<previous.end: raise ValueError('overlapping input')
                if next(expected_slots(previous.end,bar.start,base_tf,calendar),None) is not None: segment+=1
            segmented.append(replace(bar,segment_id=str(segment))); previous=bar
        base=tuple(segmented)
        start=utc(history_start) if history_start else base[0].start
        if start>clock or (start.timestamp()/60)%duration: raise ValueError('invalid history_start')
        base=tuple(b for b in base if b.start>=start)
        horizon=clock-timedelta(seconds=clock.timestamp()%(duration*60))
        wanted=set(expected_slots(start,horizon,base_tf,calendar)); present={b.start for b in base}
        missing=sorted(wanted-present)
        feed['coverage']={'status':'INCOMPLETE' if missing else 'COMPLETE','expected_slots':len(wanted),'present_slots':len(wanted&present),'missing_slots':len(missing),'missing':[t.isoformat() for t in missing]}
    else:
        feed['coverage']={'status':'EMPTY','expected_slots':0,'present_slots':0}
    feed['hashes']={**feed.get('hashes',{}),'manifest':stable_id('manifest',feed.get('manifest',{})),'prefix':stable_id('feed_prefix',inst,base)}
    session_result=collect_sessions(base,inst,clock,feed.get('manifest',{}).get('sessions',()),calendar=calendar,policy=policy)
    frames=tuple(dict.fromkeys((*policy.origin_tfs,'W','D','H4','H2',*policy.entry_tfs,*(p.tf for p in session_result.liquidity))))
    bars_by_tf={}; coverage={}; support=[{'component':'session_liquidity',**dict(d)} for d in session_result.diagnostics]
    for tf in frames:
        if base and (minutes(tf) is not None and (minutes(tf)<minutes(base[0].tf) or minutes(tf)%minutes(base[0].tf))):
            coverage[tf]={'status':'UNRESOLVED_RESOLUTION','base_tf':base[0].tf}
            support.append({'component':'aggregation','tf':tf,'status':'UNRESOLVED_RESOLUTION'})
            continue
        result=aggregate(base,tf,inst,clock,calendar=calendar)
        bars_by_tf[tf]=result['bars']; coverage[tf]=result['coverage']
    gaps=gaps_from_base(base,policy)
    structures={tf:invalidate_levels(assess(analyze(bs,policy,supplemental_liquidity=tuple(p for p in session_result.liquidity if p.tf==tf)),bs,policy),gaps,policy) for tf,bs in bars_by_tf.items()}
    story_result=suspend_stories(find_stories(bars_by_tf,structures,policy),gaps,bars_by_tf,policy)
    entry_result=detect_setups(bars_by_tf,structures,story_result,inst,policy,story_events=story_result.events,eligibility_start=lower)
    candidates=sorted((s for s in entry_result.setups if (lower is None or s.available_at>=lower) and s.available_at<=clock),key=lambda s:(s.available_at,policy.entry_tfs.index(s.tf) if s.tf in policy.entry_tfs else len(policy.entry_tfs),s.id))
    stories={s.id:s for s in story_result.stories}
    orders=[]; rejected=[]; actions=[dict(a) for a in management_actions]; execution_cache={}
    economic_signals={}
    aliases=[]
    alternatives=policy.source_profile in ('source_all','all_routes')
    for setup in candidates:
        if setup.status!='ELIGIBLE': continue
        story=stories[setup.story_id]
        if story.details.get('owner_selection')=='BLOCKED_COUNTERWEEKLY':
            rejected.append({'setup_id':setup.id,'reason':'BLOCKED_COUNTERWEEKLY'}); continue
        # Same pattern/level/clock/risk from another context is one signal.
        # Later confirmations remain distinct; source_all retains alternatives.
        economic_key=stable_id('economic_signal',setup.instrument,setup.tf,setup.side,setup.model,setup.level_id,setup.available_at,setup.entry_ticks,setup.stop_ticks,setup.target_ticks,setup.order_type,setup.expires_at)
        if not alternatives and economic_key in economic_signals:
            canonical=economic_signals[economic_key]
            aliases.append({'setup_id':setup.id,'story_id':setup.story_id,'canonical_setup_id':canonical.setup_id,'order_id':canonical.id,'economic_signal_id':economic_key})
            continue
        # Prospective cap uses only execution information available at submission.
        # Censored exposure remains reserved: unknown execution is not a free slot.
        active=0
        if not alternatives:
            for previous in orders:
                key=(previous.id,setup.available_at)
                if key not in execution_cache:
                    execution_cache[key]=simulate((previous,),tuple(b for b in base if b.available_at<=setup.available_at),inst,costs,setup.available_at,actions,calendar=calendar)
                obs=execution_cache[key]['observations']
                if not obs or obs[0].get('outcome') not in ('WIN','LOSS','BREAK_EVEN','CANCELLED','REPLACED','EXPIRED'):
                    active+=1
            if active>=max_open_orders:
                rejected.append({'setup_id':setup.id,'reason':'EXPOSURE_CAP'}); continue
        order=Order(id=stable_id('order',setup.id,policy.id),setup_id=setup.id,instrument=setup.instrument,tf=setup.tf,model=setup.model,side=setup.side,kind=setup.order_type,clock=setup.clock,entry_ticks=setup.entry_ticks,stop_ticks=setup.stop_ticks,target_ticks=setup.target_ticks,expires_at=setup.expires_at,details={'story_id':setup.story_id,'policy_id':policy.id,'economic_signal_id':economic_key,'context_policy':'first_causal_context_canonical'})
        orders.append(order)
        economic_signals[economic_key]=order
        for event in story_result.events:
            if event.reference_id==setup.story_id and (event.kind in ('STORY_INVALIDATED','STORY_DESTINATION_REACHED','STORY_CANCELLED','STORY_FLIPPED') or event.details.get('pending_action')=='CANCEL_DEPENDENT') and event.available_at>=setup.available_at:
                actions.append({'order_id':order.id,'kind':'CANCEL','available_at':event.available_at,'reason':event.kind})
    known_orders={o.id for o in orders}
    if any(a.get('order_id') not in known_orders for a in management_actions):
        raise ValueError('management action references unknown or unselected order')
    execution=simulate(orders,base,inst,costs,clock,actions,calendar=calendar)
    support.extend(story_result.support); support.extend(entry_result.support)
    unavailable=[tf for tf in (*policy.origin_tfs,*policy.entry_tfs) if not bars_by_tf.get(tf)]
    support.extend({'component':'required_history','tf':tf,'status':'INSUFFICIENT_COMPLETE_BARS'} for tf in dict.fromkeys(unavailable))
    degraded=not base or feed['coverage']['status']!='COMPLETE' or bool(unavailable) or any(v['status']=='UNRESOLVED_RESOLUTION' for v in coverage.values())
    result={'schema_version':'bishop_offline_v2_1','run_id':stable_id('run','selection_dedup_v1',feed.get('hashes'),clock,lower,policy.id,costs,max_open_orders,management_actions),
            'status':'PARTIAL_UNVALIDATED' if degraded else 'COMPUTED_UNVALIDATED','as_of':clock,'scan_start':lower,'instrument':inst,'input':feed.get('hashes',{}),'policy':policy,'costs':costs,
            'selection':{'mode':'INDEPENDENT_ALTERNATIVES' if alternatives else 'PROSPECTIVE_CAPPED','max_open_orders':None if alternatives else max_open_orders,'rejected':rejected,'aliases':aliases,'dedup_policy':'same_model_level_clock_risk_v1_first_context'},
            'coverage':{'base':feed.get('coverage',{}),'timeframes':coverage},'support':support,
            'stories':story_result.stories,'story_events':story_result.events,'data_gap_events':gaps,'setups':candidates,'orders':orders,'actions':actions,
            'execution_events':execution['events'],'observations':execution['observations'],'positions':execution['positions'],
            'summary':{'stories':len(story_result.stories),'setups':len(candidates),'orders':len(orders),'outcomes':dict(Counter(o.get('outcome','UNKNOWN') for o in execution['observations']))},
            'teacher_acceptance':'NOT_REPLAYED','limitations':['OHLC execution censors ambiguous intrabar sequences.','Numerical policies are implementation choices; teacher replay acceptance is pending.']}
    if include_diagnostics: result['diagnostics']={'structures':structures,'entry_events':entry_result.events,'imbalances':entry_result.imbalances,'reactions':story_result.reactions}
    return jsonable(result)
