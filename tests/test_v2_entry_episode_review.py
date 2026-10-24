"""Independent entry reaction-episode retirement and anticipatory pool checks."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from bishop.v2.entries import _pool_taken_before,_reaction_episode_reason
from bishop.v2.types import Bar,Event,Clock,Liquidity
T=datetime(2026,1,1,tzinfo=timezone.utc)

def pool(ident,price):
    return Liquidity(id=ident,instrument='X',tf='H1',kind='LOW',price_ticks=price,formed_at=T,available_at=T)


def bar(hour,segment='0'):
    return Bar('X','H1',T+timedelta(hours=hour),T+timedelta(hours=hour+1),
               100,105,95,100,segment_id=segment)


def event(kind,hour,side='BUY',scope='root',reference='level'):
    at=T+timedelta(hours=hour)
    return Event(id=f'{kind}_{hour}_{scope}_{side}',kind=kind,instrument='X',tf='H4',
                 clock=Clock(at,at,at),side=side,scope_id=scope,reference_id=reference)


def reaction():
    return (bar(1),SimpleNamespace(id='level'),event('BREAKOUT',1),())


def test_role_flip_back_does_not_revive_original_reaction():
    events=(event('LEVEL_ROLE_CHANGE',3,'SELL'),event('LEVEL_ROLE_CHANGE',4,'BUY'))
    assert _reaction_episode_reason(reaction(),bar(5),events)=='reaction_H4_level_role_lost'


def test_gap_and_same_scope_break_retire_reaction_without_global_child_veto():
    assert _reaction_episode_reason(reaction(),bar(5,'new'),())=='reaction_data_segment_changed'
    assert _reaction_episode_reason(reaction(),bar(5),(event('RANGE_BROKEN',4),))=='reaction_H4_scope_broken'
    assert _reaction_episode_reason(reaction(),bar(5),(event('BREAKOUT',4),))=='reaction_replaced_by_fresh_H4_break'
    assert _reaction_episode_reason(reaction(),bar(5),(event('RANGE_BROKEN',4,scope='child'),)) is None
    assert _reaction_episode_reason(reaction(),bar(5),(event('BREAKOUT',6),)) is None


def test_pool_consumption_is_observed_before_reaction_not_future_sweep_veto():
    p=pool('l',96)
    taken=bar(1)
    assert _pool_taken_before(p,bar(3),(taken,))
    future=bar(4)
    assert not _pool_taken_before(p,bar(3),(future,))
    delayed=Bar('X','H1',taken.start,taken.end,100,105,95,100,
                available_at=T+timedelta(hours=5))
    assert not _pool_taken_before(p,bar(3),(delayed,))


def test_native_gap_level_retirement_is_causal_terminal_and_index_equivalent():
    from bishop.v2.structure import analyze,role_at,RoleIndex
    from bishop.v2.types import StrategyPolicy
    before=(Bar('X','H1',T,T+timedelta(hours=1),100,101,99,100),
            Bar('X','H1',T+timedelta(hours=1),T+timedelta(hours=2),100,111,99,110),
            Bar('X','H1',T+timedelta(hours=2),T+timedelta(hours=3),110,111,99,100))
    post=Bar('X','H1',T+timedelta(hours=4),T+timedelta(hours=5),100,101,99,100,
             available_at=T+timedelta(hours=6),segment_id='new')
    short=analyze(before,StrategyPolicy())
    full=analyze((*before,post),StrategyPolicy())
    level=next(l for l in short.levels if l.kind=='A')
    assert full.levels[:len(short.levels)]==short.levels
    assert tuple(e for e in full.events if e.available_at<=before[-1].available_at)==short.events
    retired=next(e for e in full.events if e.kind=='LEVEL_UNAVAILABLE' and e.reference_id==level.id)
    assert retired.available_at==post.available_at
    later=event('LEVEL_ROLE_CHANGE',7,'BUY',reference=level.id)
    events=(*full.events,later)
    index=RoleIndex(events)
    assert role_at(level,index,T+timedelta(hours=5))==level.side
    for hour in (3,5,6,7,8):
        at=T+timedelta(hours=hour)
        assert role_at(level,index,at)==role_at(level,events,at)
    assert role_at(level,index,T+timedelta(hours=8)) is None
