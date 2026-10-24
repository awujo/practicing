"""Independent cross-timeframe observation-gap integrity checks."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from bishop.v2.types import Bar,Clock,Level,Story,StrategyPolicy,Event
from bishop.v2.structure import StructureResult,role_at,RoleIndex
from bishop.v2.stories import StoryResult
from bishop.v2.continuity import gaps_from_base,invalidate_levels,suspend_stories
from bishop.v2.entries import _is_active

T=datetime(2026,1,5,tzinfo=timezone.utc)
P=StrategyPolicy()


def base_gap(receipt=4,left_receipt=1):
    left=Bar('X','H1',T,T+timedelta(hours=1),100,101,99,100,
             available_at=T+timedelta(hours=left_receipt),segment_id='old')
    right=Bar('X','H1',T+timedelta(hours=3),T+timedelta(hours=4),100,101,99,100,
              available_at=T+timedelta(hours=receipt),segment_id='new')
    return left,right


def weekly_level():
    return Level(id='weekly',instrument='X',tf='W',kind='V',price_ticks=90,side='BUY',
                 formed_at=T-timedelta(days=7),available_at=T-timedelta(days=6))


def story(ident,origin):
    return Story(id=ident,instrument='X',side='BUY',origin_tf='D',level_tf='W',
                 confirmation_tf='H4',route='test',source_profile='bishop_confirmation',
                 clock=Clock(origin.end,origin.end,origin.available_at),origin_id='r',
                 confirmation_id='c',details={'reaction_bar_id':origin.id})


def test_base_gap_retires_weekly_level_before_week_close_but_not_before_receipt():
    left,right=base_gap(receipt=6)
    gaps=gaps_from_base((left,right),P)
    level=weekly_level()
    original=StructureResult((),(level,),(),(),())
    result=invalidate_levels(original,gaps,P)
    index=RoleIndex(result.events)
    assert role_at(level,index,T+timedelta(hours=5))=='BUY'
    assert role_at(level,index,T+timedelta(hours=6)) is None
    assert result.events[0].available_at < T+timedelta(days=7)
    assert result.events[0].details['market_reversal'] is False
    assert original.events==()
    assert tuple(e for e in result.events if e.available_at<=left.available_at)==original.events


def test_old_story_suspended_new_origin_retained_without_market_flip_or_position_close():
    left,right=base_gap()
    old_origin=Bar('X','D',T-timedelta(days=1),T,100,101,99,100)
    fresh_origin=Bar('X','D',T+timedelta(days=1),T+timedelta(days=2),100,101,99,100)
    old,fresh=story('old',old_origin),story('fresh',fresh_origin)
    original=StoryResult((old,fresh),(),(),())
    result=suspend_stories(original,gaps_from_base((left,right),P),{'D':(old_origin,fresh_origin)},P)
    assert result.stories==original.stories
    assert len(result.events)==1 and result.events[0].reference_id=='old'
    event=result.events[0]
    assert event.kind=='STORY_SUSPENDED' and event.evidence_status=='UNKNOWN'
    assert event.details['pending_action']=='CANCEL_DEPENDENT'
    assert event.details['position_action']=='NONE' and event.details['market_reversal'] is False
    assert _is_active(old,T+timedelta(hours=3),result.events)
    assert not _is_active(old,T+timedelta(hours=4),result.events)
    assert _is_active(fresh,fresh.available_at,result.events)


def test_gap_event_cannot_precede_publication_of_a_hashed_source_dependency():
    left,right=base_gap(receipt=4,left_receipt=10)
    event=gaps_from_base((left,right),P)[0]
    assert event.available_at>=max(left.available_at,right.available_at)


def test_late_internal_bar_does_not_erase_previously_observed_gap_history():
    from bishop.v2.engine import run
    from bishop.v2.types import Instrument
    from bishop.v2.simulation import Costs
    first=Bar('X','H1',T,T+timedelta(hours=1),100,101,99,100)
    delayed=Bar('X','H1',T+timedelta(hours=1),T+timedelta(hours=2),100,101,99,100,
                available_at=T+timedelta(hours=5))
    third=Bar('X','H1',T+timedelta(hours=2),T+timedelta(hours=3),100,101,99,100)
    instrument=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    policy=StrategyPolicy(origin_tfs=('H4',),entry_tfs=('H1',))
    early=run({'instrument':instrument,'bars':(first,third)},as_of=third.end,
              policy=policy,costs=Costs())
    assert early['data_gap_events']  # Actual early observation, not invented market information.
    try:
        later=run({'instrument':instrument,'bars':(first,delayed,third)},
                  as_of=delayed.available_at,policy=policy,costs=Costs())
    except ValueError as exc:
        # An explicit unsupported-publication policy may fail closed until
        # the engine supports receipt-ordered replay and gap resolution events.
        assert any(word in str(exc).lower() for word in ('publication','availability','late','chronolog'))
        return
    cutoff=third.end.isoformat()
    assert early['data_gap_events']==[event for event in later['data_gap_events']
                                     if event['clock']['available_at']<=cutoff]
