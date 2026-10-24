"""Independent first-liquidity-take to later reaction linkage; synthetic clocks only."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from bishop.v2.types import Bar,Clock,Event,Liquidity,Level
from bishop.v2.entries import _first_take_for_reaction

T=datetime(2026,1,1,tzinfo=timezone.utc)


def bar(hour,high=105,close=104,segment='0',received=None):
    return Bar('X','H1',T+timedelta(hours=hour),T+timedelta(hours=hour+1),100,
               high,98,close,segment_id=segment,
               available_at=T+timedelta(hours=received) if received is not None else None)


def event(kind,hour,side='SELL',scope='root',reference='level'):
    at=T+timedelta(hours=hour)
    return Event(id=f'{kind}_{hour}_{side}_{scope}',kind=kind,instrument='X',tf='H4',
                 clock=Clock(at,at,at),side=side,scope_id=scope,reference_id=reference)


def objects(parent_hour=0):
    pool=Liquidity(id='pool',instrument='X',tf='H4',kind='HIGH',price_ticks=102,
                   formed_at=T,available_at=T)
    level=Level(id='level',instrument='X',tf='H4',kind='A',price_ticks=100,side='SELL',
                formed_at=T,available_at=T)
    return pool,level,event('BREAKOUT',parent_hour)


def test_first_take_retained_for_later_rejection_without_repeat_sweep():
    pool,level,parent=objects()
    first=bar(1)
    reaction=bar(3,high=101,close=99)
    assert _first_take_for_reaction(pool,reaction,(first,reaction),level,parent,()) is first


@pytest.mark.parametrize('events',[
    (event('LEVEL_ROLE_CHANGE',2.5,'BUY'),event('LEVEL_ROLE_CHANGE',3,'SELL')),
    (event('RANGE_BROKEN',2.5),),
    (event('LEVEL_UNAVAILABLE',2.5),),
    (event('BREAKOUT',2.5),),
])
def test_lost_episode_cannot_reuse_first_pool_take(events):
    pool,level,parent=objects()
    first=bar(1)
    reaction=bar(3,high=101,close=99)
    assert _first_take_for_reaction(pool,reaction,(first,reaction),level,parent,events) is None


def test_role_loss_before_first_take_does_not_disappear_when_role_flips_back():
    pool,level,parent=objects()
    first=bar(2)
    reaction=bar(4,high=101,close=99)
    events=(event('LEVEL_ROLE_CHANGE',1,'BUY'),event('LEVEL_ROLE_CHANGE',2,'SELL'))
    assert _first_take_for_reaction(pool,reaction,(first,reaction),level,parent,events) is None


def test_earlier_episode_first_take_cannot_be_replaced_by_later_take():
    pool,level,parent=objects(parent_hour=2)
    first,later=bar(1),bar(2)
    reaction=bar(3,high=101,close=99)
    assert _first_take_for_reaction(pool,reaction,(first,later,reaction),level,parent,()) is None


def test_future_and_delayed_takes_cannot_authorize_current_reaction():
    pool,level,parent=objects()
    reaction=bar(3,high=101,close=99)
    assert _first_take_for_reaction(pool,reaction,(bar(1,received=5),reaction,bar(4)),level,parent,()) is None
    first=bar(1)
    assert _first_take_for_reaction(pool,reaction,(first,reaction,bar(4)),level,parent,()) is first


def test_gap_blocks_take_link_but_unrelated_child_event_does_not():
    pool,level,parent=objects()
    first=bar(1)
    assert _first_take_for_reaction(pool,bar(3,high=101,close=99,segment='new'),
                                    (first,),level,parent,()) is None
    reaction=bar(3,high=101,close=99)
    assert _first_take_for_reaction(pool,reaction,(first,reaction),level,parent,
                                    (event('RANGE_BROKEN',2.5,scope='child'),)) is first


def test_first_take_event_history_does_not_require_a_future_rejection():
    from bishop.v2.entries import detect_setups
    from bishop.v2.structure import StructureResult
    from bishop.v2.types import Instrument,StrategyPolicy
    pool=Liquidity(id='h4_pool',instrument='X',tf='H4',kind='HIGH',price_ticks=104,
                   formed_at=T+timedelta(hours=4),available_at=T+timedelta(hours=4),
                   form='BAR',details={'role':'IRL'})
    level=Level(id='h4_level',instrument='X',tf='H4',kind='A',price_ticks=100,side='SELL',
                formed_at=T,available_at=T)
    parent=event('BREAKOUT',0,reference='h4_level')
    h4=StructureResult((),(level,),(pool,),(parent,),())
    h1=StructureResult((),(),(),(),())
    first=bar(4,high=105,close=104)
    rejection=bar(6,high=102,close=99)
    story=SimpleNamespace(id='story',side='SELL',available_at=T,clock=Clock(T,T,T),details={})
    policy=StrategyPolicy(entry_tfs=('H1',),origin_tfs=('D',))
    instrument=Instrument('X','1','1',calendar_id='24x7_utc_v1')
    early=detect_setups({'H1':(first,),'H4':()}, {'H1':h1,'H4':h4},(story,),instrument,policy)
    later=detect_setups({'H1':(first,rejection),'H4':()}, {'H1':h1,'H4':h4},(story,),instrument,policy)
    later_takes=tuple(e for e in later.events if e.kind=='LIQUIDITY_FIRST_TAKEN'
                      and e.available_at<=first.available_at)
    early_takes=tuple(e for e in early.events if e.kind=='LIQUIDITY_FIRST_TAKEN')
    assert later_takes
    assert early_takes==later_takes
    take=later_takes[0]
    assert take.reference_id==pool.id and take.bar_ids==(first.id,)
    assert pool.id in take.evidence_ids


def test_normal_confirmation_setup_links_actual_first_take_event(monkeypatch):
    import bishop.v2.entries as entries
    from bishop.v2.structure import StructureResult
    from bishop.v2.types import Instrument,StrategyPolicy
    pool=Liquidity(id='h4_pool',instrument='X',tf='H4',kind='HIGH',price_ticks=104,
                   formed_at=T+timedelta(hours=4),available_at=T+timedelta(hours=4),
                   form='BAR',details={'role':'IRL'})
    level=Level(id='h4_level',instrument='X',tf='H4',kind='A',price_ticks=100,side='SELL',
                formed_at=T,available_at=T)
    lower_level=Level(id='lower_level',instrument='X',tf='H1',kind='A',price_ticks=98,side='SELL',
                      formed_at=T,available_at=T)
    parent=event('BREAKOUT',0,reference=level.id)
    first=bar(4,high=105,close=104)
    rejection=bar(6,high=102,close=99)
    confirmation=Bar('X','H1',T+timedelta(hours=7),T+timedelta(hours=8),100,101,96,97)
    lower_break=Event(id='lower_break',kind='BREAKOUT',instrument='X',tf='H1',
                      clock=Clock(confirmation.end,confirmation.end,confirmation.available_at),side='SELL',
                      reference_id=lower_level.id,bar_ids=(confirmation.id,))
    structures={'H4':StructureResult((),(level,),(pool,),(parent,),()),
                'H1':StructureResult((),(lower_level,),(),(lower_break,),())}
    story=SimpleNamespace(id='story',side='SELL',available_at=T,clock=Clock(T,T,T),details={})
    monkeypatch.setattr(entries,'plan',lambda *a,**k:SimpleNamespace(stop_ticks=106,target_ticks=90,
                        status='ELIGIBLE',details={'unresolved_reasons':[]}))
    warmup=tuple(bar(hour,high=101,close=100) for hour in range(4))
    h4_bar=Bar('X','H4',T,T+timedelta(hours=4),100,104,98,101)
    result=entries.detect_setups({'H1':(*warmup,first,rejection,confirmation),'H4':(h4_bar,)},structures,
                                (story,),Instrument('X','1','1',calendar_id='24x7_utc_v1'),
                                StrategyPolicy(entry_tfs=('H1',),origin_tfs=('D',)))
    setup=next(s for s in result.setups if s.model=='confirmation_bo')
    take=next(e for e in result.events if e.kind=='LIQUIDITY_FIRST_TAKEN' and e.reference_id==pool.id)
    assert take.bar_ids==(first.id,) and pool.id in take.evidence_ids
    assert take.id in setup.evidence_ids
    assert take.available_at<=setup.available_at
    assert rejection.id in setup.evidence_ids and lower_break.id in setup.evidence_ids


def test_equal_liquidity_touch_is_not_first_strict_take():
    pool,level,parent=objects()
    equality=bar(1,high=102,close=101)
    rejection=bar(3,high=101,close=99)
    assert _first_take_for_reaction(pool,rejection,(equality,rejection),level,parent,()) is None


def test_buy_side_first_low_take_can_link_to_later_rejection():
    pool=Liquidity(id='low_pool',instrument='X',tf='H4',kind='LOW',price_ticks=98,
                   formed_at=T,available_at=T)
    level=Level(id='buy_level',instrument='X',tf='H4',kind='V',price_ticks=100,side='BUY',
                formed_at=T,available_at=T)
    parent=event('BREAKOUT',0,side='BUY',reference=level.id)
    first=Bar('X','H1',T+timedelta(hours=1),T+timedelta(hours=2),100,101,95,96)
    rejection=Bar('X','H1',T+timedelta(hours=3),T+timedelta(hours=4),100,102,99,101)
    assert _first_take_for_reaction(pool,rejection,(first,rejection),level,parent,()) is first
