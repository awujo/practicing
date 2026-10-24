"""Independent integration invariants; no teacher-example acceptance claims."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from bishop.v2.types import Bar, Clock, Event, Instrument, StrategyPolicy, stable_id

T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_evidence_details_are_deeply_immutable_and_identity_serializable():
    source = {'refs': [{'price': 12}]}
    event = Event(id='e', kind='SWEEP', instrument='X', tf='M1',
                  clock=Clock(T, T + timedelta(minutes=1), T + timedelta(minutes=2)),
                  details=source)
    identity = stable_id('evidence', event)
    source['refs'][0]['price'] = 99
    assert event.details['refs'][0]['price'] == 12
    assert stable_id('evidence', event) == identity
    with pytest.raises(TypeError):
        event.details['refs'][0]['price'] = 7


def test_bar_corrections_change_identity_without_publication_latency_changing_price_identity():
    args = dict(instrument='X', tf='M1', start=T, end=T+timedelta(minutes=1),
                open_ticks=10, high_ticks=12, low_ticks=9, close_ticks=11)
    a = Bar(**args)
    delayed = Bar(**args, available_at=T+timedelta(minutes=2))
    corrected = Bar(**{**args, 'high_ticks': 13})
    assert a.id == delayed.id
    assert a.id != corrected.id
    assert delayed.clock.available_at > a.clock.available_at


def test_price_grid_and_policy_identity_preserve_declared_choices():
    instrument = Instrument('OIL', Decimal('0.01'), Decimal('1'))
    assert instrument.to_ticks('-0.12') == -12
    with pytest.raises(ValueError):
        instrument.to_ticks('1.001')
    assert StrategyPolicy(oc_gap_ticks=0).id != StrategyPolicy(oc_gap_ticks=1).id
    with pytest.raises(ValueError):
        Clock(T, T+timedelta(minutes=2), T+timedelta(minutes=1))


def test_aggregation_reports_completely_missing_nominal_bin():
    from bishop.v2.aggregation import aggregate
    bars = tuple(Bar('X', 'M1', T+timedelta(minutes=i), T+timedelta(minutes=i+1),
                     10, 11, 9, 10) for i in (*range(60), *range(120, 180)))
    result = aggregate(bars, 'H1', calendar='24x7_utc_v1', anchor='utc_epoch_v1',
                       as_of=T+timedelta(hours=3))
    assert result['coverage']['status'] != 'COMPLETE'
    assert any(row['start'] == (T+timedelta(hours=1)).isoformat()
               for row in result['coverage']['incomplete'])


def test_destination_lifecycle_event_blocks_later_entry_eligibility():
    from types import SimpleNamespace
    from bishop.v2.entries import _is_active
    story = SimpleNamespace(id='story')
    event = Event(id='end', kind='STORY_DESTINATION_REACHED', instrument='X', tf='D',
                  clock=Clock(T,T,T), reference_id='story')
    assert not _is_active(story, T+timedelta(minutes=1), (event,))


def test_counterweekly_story_schema_activates_nearer_target_guard():
    from types import SimpleNamespace
    from bishop.v2.risk import plan
    from bishop.v2.types import Level
    level = Level(id='obstacle', instrument='X', tf='H1', kind='A', price_ticks=110,
                  side='SELL', formed_at=T, available_at=T)
    story = SimpleNamespace(destination_ticks=150, destination_ref_id='dest',
                            details={'initial_weekly_relation':'COUNTER_WEEKLY',
                                     'counterweekly_target_guard_required':True})
    from bishop.v2.types import Liquidity
    pool=Liquidity(id='external',instrument='X',tf='H1',kind='HIGH',price_ticks=130,formed_at=T,available_at=T)
    active=SimpleNamespace(id='range',version_id='v',available_at=T,status='DEFINED',
                           details={'endpoint_stage':'CONFIRMED_DELIVERY'},direction='BUY',
                           origin_ticks=80,endpoint_ticks=130,protected_liquidity_id=None,
                           endpoint_liquidity_id=pool.id)
    result = plan('BUY',100,T,'H1',(),(level,),(pool,),story,
                  Instrument('X','1','1'),StrategyPolicy(risk_profile='fixed11'),ranges=(active,))
    assert result.target_ticks == 110
    absent=plan('BUY',100,T,'H1',(),(level,),(),story,
                Instrument('X','1','1'),StrategyPolicy(risk_profile='fixed11'))
    assert absent.target_ticks is None and absent.status == 'UNRESOLVED'


@pytest.mark.parametrize('change', [dict(source_profile='misspelled'), dict(risk_profile='nonsense'),
                                   dict(target_profile='nonsense'), dict(near_atr_period=True),
                                   dict(near_atr_period=1.5), dict(allow_counterweekly='false')])
def test_invalid_strategy_policy_fails_before_market_evaluation(change):
    with pytest.raises(ValueError):
        StrategyPolicy(**change)


def test_boundary_cancellation_wins_over_expiry_even_at_last_observed_close():
    from bishop.v2.simulation import simulate, Costs
    from bishop.v2.types import Order
    end=T+timedelta(minutes=1)
    order=Order(id='o',setup_id='s',instrument='X',tf='M1',model='test',side='BUY',
                kind='LIMIT',clock=Clock(T,T,T),entry_ticks=8,stop_ticks=5,
                target_ticks=12,expires_at=end)
    bar=Bar('X','M1',T,end,10,11,9,10)
    result=simulate((order,),(bar,),Instrument('X','1','1',calendar_id='24x7_utc_v1'),
                    Costs(),end,actions=({'order_id':'o','kind':'CANCEL','at':end},))
    assert result['observations'][0]['status']=='CANCELLED'


def test_late_old_run_cannot_replace_newer_order_projection():
    from bishop.paper_store import Store
    store=Store()
    base=dict(schema='test',status='COMPUTED',instrument={},input={},policy={},coverage={})
    new={**base,'as_of':(T+timedelta(hours=2)).isoformat(),
         'orders':[{'id':'same_order','status':'FILLED'}]}
    old={**base,'as_of':(T+timedelta(hours=1)).isoformat(),
         'orders':[{'id':'same_order','status':'PENDING'}]}
    store.persist_result(new,'new')
    try:
        store.persist_result(old,'old')
    except ValueError:
        pass  # Rejecting a stale write is also valid.
    assert store.list('orders')[0]['status']=='FILLED'


def test_engine_mapping_rejects_incorrect_duration_and_marks_missing_resolution():
    from bishop.v2.engine import run
    from bishop.v2.simulation import Costs
    inst=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    bad=Bar('X','H1',T,T+timedelta(minutes=30),10,11,9,10)
    with pytest.raises(ValueError):
        run({'instrument':inst,'bars':(bad,)},as_of=T+timedelta(hours=1),costs=Costs())
    empty=run({'instrument':inst,'bars':()},as_of=T,costs=Costs())
    assert empty['status']=='PARTIAL_UNVALIDATED'
    good=Bar('X','H1',T,T+timedelta(hours=1),10,11,9,10)
    coarse=run({'instrument':inst,'bars':(good,)},as_of=T+timedelta(hours=1),costs=Costs(),
               policy=StrategyPolicy(entry_tfs=('M5',),origin_tfs=('D',)))
    assert coarse['status']=='PARTIAL_UNVALIDATED'
    assert coarse['coverage']['timeframes']['M5']['status']=='UNRESOLVED_RESOLUTION'


def test_engine_confirmed_flip_cancels_existing_pending_order(monkeypatch):
    from types import SimpleNamespace
    import bishop.v2.engine as engine
    from bishop.v2.types import Setup
    from bishop.v2.simulation import Costs
    inst=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    bars=tuple(Bar('X','M1',T+timedelta(minutes=i),T+timedelta(minutes=i+1),10,11,9,10) for i in range(3))
    story=SimpleNamespace(id='story',details={})
    flip=Event(id='flip',kind='STORY_FLIPPED',instrument='X',tf='H1',
               clock=Clock(T+timedelta(minutes=1),T+timedelta(minutes=1),T+timedelta(minutes=1)),
               reference_id='story')
    setup=Setup(id='s',instrument='X',tf='M1',model='test',side='BUY',story_id='story',
                clock=Clock(T,T,T),entry_ticks=8,stop_ticks=5,target_ticks=12,risk_profile='fixed11')
    monkeypatch.setattr(engine,'find_stories',lambda *a:SimpleNamespace(stories=(story,),events=(flip,),support=()))
    monkeypatch.setattr(engine,'detect_setups',lambda *a,**k:SimpleNamespace(setups=(setup,),support=()))
    monkeypatch.setattr(engine,'jsonable',lambda x:x)
    result=engine.run({'instrument':inst,'bars':bars},as_of=bars[-1].end,costs=Costs(),
                      policy=StrategyPolicy(entry_tfs=('M1',),origin_tfs=('D',)))
    assert result['observations'][0]['status']=='CANCELLED'
    assert result['actions'][0]['reason']=='STORY_FLIPPED'


def test_nonempty_complete_pipeline_preserves_causal_story_setup_prefix():
    import random
    from bishop.v2.engine import run
    from bishop.v2.simulation import Costs
    randomizer=random.Random(41)
    price=1000
    bars=[]
    for i in range(72):
        close=price+randomizer.choice((-12,-8,-4,4,8,12))
        bars.append(Bar('X','H1',T+timedelta(hours=i),T+timedelta(hours=i+1),
                        price,max(price,close)+3,min(price,close)-3,close))
        price=close
    inst=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    policy=StrategyPolicy(origin_tfs=('H4',),entry_tfs=('H1',),risk_profile='fixed11',
                          target_profile='fixed3r',source_profile='source_all')
    early=run({'instrument':inst,'bars':bars[:48]},as_of=bars[47].end,policy=policy,costs=Costs())
    later=run({'instrument':inst,'bars':bars},as_of=bars[-1].end,policy=policy,costs=Costs())
    cutoff=bars[47].end.isoformat()
    assert early['stories'] and early['setups'] and early['orders']
    for collection in ('stories','setups','orders','story_events','execution_events'):
        expected=[row for row in later[collection] if row['clock']['available_at']<=cutoff]
        assert early[collection] == expected, collection


def test_impulse_cannot_read_unpublished_close_before_atr_window():
    from bishop.v2.impulse import assess
    from bishop.v2.structure import StructureResult
    bars=(Bar('X','M1',T,T+timedelta(minutes=1),100,100,100,100,
              available_at=T+timedelta(minutes=10)),
          Bar('X','M1',T+timedelta(minutes=1),T+timedelta(minutes=2),10,11,9,10),
          Bar('X','M1',T+timedelta(minutes=2),T+timedelta(minutes=3),10,20,9,20))
    event=Event(id='role',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='M1',
                clock=Clock(bars[2].end,bars[2].end,bars[2].available_at),
                bar_ids=(bars[2].id,),side='BUY')
    result=assess(StructureResult((),(),(),(event,),()),bars,
                  StrategyPolicy(impulse_atr_period=1,impulse_atr_fraction='0.5'))
    assessment=next(e for e in result.events if e.kind=='IMPULSE_ASSESSMENT')
    assert assessment.evidence_status=='UNKNOWN'


def test_explicit_session_missing_slot_never_publishes_partial_extrema():
    from bishop.v2.sessions import collect_sessions
    inst=Instrument('X','1','1',calendar_id='24x7_utc_v1')
    bars=tuple(Bar('X','M1',T+timedelta(minutes=i),T+timedelta(minutes=i+1),10,11+i,9,10)
               for i in (0,2))
    spec=({'id':'short','timezone':'UTC','start':'00:00','end':'00:03'},)
    missing=collect_sessions(bars,inst,T+timedelta(minutes=3),spec)
    assert not missing.liquidity
    assert any(d['status']=='MISSING_SLOTS' for d in missing.diagnostics)
    middle=Bar('X','M1',T+timedelta(minutes=1),T+timedelta(minutes=2),10,50,1,10,
               available_at=T+timedelta(minutes=4))
    delayed=collect_sessions((bars[0],middle,bars[1]),inst,T+timedelta(minutes=3),spec)
    assert not delayed.liquidity
    complete=collect_sessions((bars[0],middle,bars[1]),inst,T+timedelta(minutes=4),spec)
    assert len(complete.liquidity)==2
    assert all(p.available_at==middle.available_at for p in complete.liquidity)
    assert {p.price_ticks for p in complete.liquidity}=={1,50}


def test_role_index_matches_reference_with_same_clock_ties_and_unborn_level():
    from bishop.v2.structure import role_at,RoleIndex
    from bishop.v2.types import Level
    level=Level(id='l',instrument='X',tf='M1',kind='V',price_ticks=10,side='BUY',
                formed_at=T,available_at=T+timedelta(minutes=1))
    events=tuple(Event(id=ident,kind='LEVEL_ROLE_CHANGE',instrument='X',tf='M1',
                       clock=Clock(at,at,at),reference_id='l',side=side)
                 for ident,side,at in (('z','SELL',T+timedelta(minutes=2)),
                                      ('a','BUY',T+timedelta(minutes=2)),
                                      ('b','BUY',T+timedelta(minutes=3))))
    index=RoleIndex(events)
    for minutes in (0,1,2,3,4):
        at=T+timedelta(minutes=minutes)
        assert role_at(level,index,at)==role_at(level,events,at)
    assert role_at(level,index,T+timedelta(minutes=2))=='SELL'


@pytest.mark.parametrize('kind,field', [('MANUAL_CLOSE','price_ticks'),('AMEND','stop_ticks')])
def test_management_rejects_nonfinite_price_at_terminal_boundary(kind,field):
    from bishop.v2.simulation import simulate,Costs
    from bishop.v2.types import Order
    end=T+timedelta(minutes=1)
    order=Order(id='o',setup_id='s',instrument='X',tf='M1',model='test',side='BUY',
                kind='MARKET',clock=Clock(T,T,T),entry_ticks=10,stop_ticks=5,target_ticks=20)
    bar=Bar('X','M1',T,end,10,11,9,10)
    with pytest.raises(ValueError):
        simulate((order,),(bar,),Instrument('X','1','1',calendar_id='24x7_utc_v1'),Costs(),end,
                 actions=({'order_id':'o','kind':kind,'at':end,field:'NaN'},))


@pytest.mark.parametrize('side,expected', [('BUY',89),('SELL',111)])
def test_zone_edge_experiment_uses_declared_far_boundary_and_requires_geometry(side,expected):
    from types import SimpleNamespace
    from bishop.v2.risk import plan
    story=SimpleNamespace(details={},destination_ticks=None,destination_ref_id=None)
    policy=StrategyPolicy(risk_profile='zone_edge',target_profile='fixed3r',stop_buffer_units='0.5')
    args=(side,100,T,'H1',(),(),(),story,Instrument('X','1','1'),policy)
    actual=plan(*args,zone_bounds=(90,110))
    assert actual.stop_ticks==expected and actual.status=='ELIGIBLE'
    assert actual.details['zone_edge_experiment'] is True
    absent=plan(*args)
    assert absent.stop_ticks is None and absent.status=='UNRESOLVED'
    assert 'zone_geometry_unresolved' in absent.details['unresolved_reasons']


def test_eligibility_start_equals_filtering_full_nonempty_entry_history():
    import random
    from bishop.v2.aggregation import aggregate
    from bishop.v2.structure import analyze
    from bishop.v2.stories import find_stories
    from bishop.v2.entries import detect_setups
    randomizer=random.Random(41);price=1000;bars=[]
    for i in range(72):
        close=price+randomizer.choice((-12,-8,-4,4,8,12))
        bars.append(Bar('X','H1',T+timedelta(hours=i),T+timedelta(hours=i+1),
                        price,max(price,close)+3,min(price,close)-3,close));price=close
    instrument=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    policy=StrategyPolicy(origin_tfs=('H4',),entry_tfs=('H1',),risk_profile='fixed11',
                          target_profile='fixed3r',source_profile='source_all')
    by_tf={tf:aggregate(bars,tf,instrument,bars[-1].end)['bars'] for tf in ('H1','H2','H4','D','W')}
    structures={tf:analyze(bs,policy) for tf,bs in by_tf.items()}
    stories=find_stories(by_tf,structures,policy)
    args=(by_tf,structures,stories,instrument,policy)
    full=detect_setups(*args,story_events=stories.events)
    cutoff=T+timedelta(hours=48)
    tail=detect_setups(*args,story_events=stories.events,eligibility_start=cutoff)
    expected=tuple(s for s in full.setups if s.available_at>=cutoff)
    assert expected and len(expected)<len(full.setups)
    assert tail.setups==expected
    assert tail.events==tuple(e for e in full.events if e.available_at>=cutoff)
    assert tail.support==full.support and tail.imbalances==full.imbalances


@pytest.mark.parametrize('profile,orders,aliases',[('bishop_confirmation',2,1),('source_all',3,0)])
def test_economic_aliases_do_not_consume_slots_and_later_confirmation_is_distinct(monkeypatch,profile,orders,aliases):
    from types import SimpleNamespace
    import bishop.v2.engine as engine
    from bishop.v2.types import Setup
    from bishop.v2.simulation import Costs
    instrument=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    bars=tuple(Bar('X','M1',T+timedelta(minutes=i),T+timedelta(minutes=i+1),10,11,9,10) for i in range(3))
    stories=tuple(SimpleNamespace(id=ident,details={}) for ident in ('story_a','story_b'))
    setups=tuple(Setup(id=ident,instrument='X',tf='M1',model='confirmation_standing_extreme',
                       side='BUY',story_id=story,clock=Clock(at,at,at),entry_ticks=8,
                       stop_ticks=5,target_ticks=12,risk_profile='context_liquidity',level_id='same_level')
                 for ident,story,at in (('a','story_a',T),('b','story_b',T),
                                        ('c','story_a',T+timedelta(minutes=1))))
    alias_end=Event(id='alias_end',kind='STORY_INVALIDATED',instrument='X',tf='M1',
                    clock=Clock(T+timedelta(minutes=1),T+timedelta(minutes=1),T+timedelta(minutes=1)),
                    reference_id='story_b')
    monkeypatch.setattr(engine,'find_stories',lambda *a:SimpleNamespace(stories=stories,events=(alias_end,),support=()))
    monkeypatch.setattr(engine,'detect_setups',lambda *a,**k:SimpleNamespace(setups=setups,support=()))
    monkeypatch.setattr(engine,'jsonable',lambda x:x)
    result=engine.run({'instrument':instrument,'bars':bars},as_of=bars[-1].end,costs=Costs(),
                      policy=StrategyPolicy(source_profile=profile,entry_tfs=('M1',),origin_tfs=('D',)),
                      max_open_orders=2)
    assert len(result['orders'])==orders
    assert len(result['selection']['aliases'])==aliases
    assert len(result['setups'])==3
    assert any(o.setup_id=='c' for o in result['orders'])
    if aliases:
        alias=result['selection']['aliases'][0]
        assert alias['setup_id']=='b' and alias['story_id']=='story_b'
        assert alias['canonical_setup_id']=='a'
        assert result['orders'][0].details['context_policy']=='first_causal_context_canonical'
        assert not result['actions']  # Alias invalidation does not invent an OR-context cancellation rule.
    else:
        assert result['selection']['mode']=='INDEPENDENT_ALTERNATIVES'
