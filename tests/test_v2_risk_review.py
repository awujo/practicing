"""Independent causal risk-state checks; numerical examples are synthetic."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from bishop.v2.types import Bar,Instrument,Liquidity,Level,StrategyPolicy
from bishop.v2.risk import plan

T=datetime(2026,1,1,tzinfo=timezone.utc)
I=Instrument('X','1','1',calendar_id='24x7_utc_v1')
S=SimpleNamespace(details={},destination_ticks=None,destination_ref_id=None)


def pool(ident,price,kind='LOW',at=T,bar_ids=()):
    return Liquidity(id=ident,instrument='X',tf='H1',kind=kind,price_ticks=price,
                     formed_at=at,available_at=at,bar_ids=bar_ids)


def rng(side,protected,target):
    return SimpleNamespace(id='r',version_id='v',available_at=T,status='DEFINED',
        details={'endpoint_stage':'CONFIRMED_DELIVERY'},direction=side,
        origin_ticks=80 if side=='BUY' else 120,endpoint_ticks=130 if side=='BUY' else 70,
        protected_liquidity_id=protected.id,endpoint_liquidity_id=target.id)


@pytest.mark.parametrize('side,bad,external',[('BUY',110,130),('SELL',90,70)])
def test_wrong_side_range_pool_cannot_produce_eligible_invalid_geometry(side,bad,external):
    protected=pool('protected',bad,'LOW' if side=='BUY' else 'HIGH')
    target=pool('external',external,'HIGH' if side=='BUY' else 'LOW')
    result=plan(side,100,T,'H1',(),(),(protected,target),S,I,StrategyPolicy(),
                ranges=(rng(side,protected,target),),protection_range_ids=('r',))
    assert result.status!='ELIGIBLE' or (result.stop_ticks<100<result.target_ticks if side=='BUY'
                                       else result.target_ticks<100<result.stop_ticks)


def test_proximity_atr_requires_current_contiguous_segment_warmup():
    old=Bar('X','H1',T,T+timedelta(hours=1),100,200,0,100,segment_id='old')
    new=Bar('X','H1',T+timedelta(hours=2),T+timedelta(hours=3),100,101,99,100,segment_id='new')
    result=plan('BUY',100,new.end,'H1',(old,new),(),(),S,I,
                StrategyPolicy(near_atr_period=2,target_profile='fixed3r'))
    assert result.details['near_ticks'] is None


def test_old_segment_level_cannot_silently_become_current_protection():
    old=Bar('X','H1',T,T+timedelta(hours=1),100,102,98,100,segment_id='old')
    new=Bar('X','H1',T+timedelta(hours=2),T+timedelta(hours=3),100,102,98,100,segment_id='new')
    level=Level(id='stale',instrument='X',tf='H1',kind='V',price_ticks=99,side='BUY',
                formed_at=old.end,available_at=old.end,bar_ids=(old.id,))
    result=plan('BUY',100,new.end,'H1',(old,new),(level,),(),S,I,
                StrategyPolicy(near_atr_period=1,target_profile='fixed3r'))
    assert 'stale' not in [item[0] for item in result.details['protected_objects']]


def test_consumed_nearby_pool_is_not_presented_as_intact_protection():
    swept=Bar('X','H1',T,T+timedelta(hours=1),100,102,90,100)
    intact=Bar('X','H1',T+timedelta(hours=1),T+timedelta(hours=2),100,102,98,100)
    taken=pool('taken',95)
    result=plan('BUY',100,intact.end,'H1',(swept,intact),(),(taken,),S,I,
                StrategyPolicy(near_atr_period=2,near_atr_fraction='1',target_profile='fixed3r'))
    assert 'taken' not in [item[0] for item in result.details['protected_objects']]


def test_latest_known_broken_range_version_cannot_be_resurrected_by_future_version():
    protected=pool('protected',80)
    target=pool('external',130,'HIGH')
    first=rng('BUY',protected,target)
    broken=SimpleNamespace(**{**first.__dict__,'version_id':'broken','available_at':T+timedelta(hours=1),'status':'BROKEN'})
    future=SimpleNamespace(**{**first.__dict__,'version_id':'future','available_at':T+timedelta(hours=3)})
    result=plan('BUY',100,T+timedelta(hours=2),'H1',(),(),(protected,target),S,I,
                StrategyPolicy(),ranges=(first,broken,future))
    assert result.details['entry_range_id'] is None
    assert result.target_ticks is None and result.status=='UNRESOLVED'


def test_target_touch_overlapping_delayed_pool_availability_is_not_known_intact():
    available=T+timedelta(minutes=30)
    protected=pool('protected',80)
    target=pool('external',130,'HIGH',at=available)
    selected=rng('BUY',protected,target)
    bar=Bar('X','H1',T,T+timedelta(hours=1),100,130,99,110)
    result=plan('BUY',100,bar.end,'H1',(bar,),(),(protected,target),S,I,
                StrategyPolicy(),ranges=(selected,))
    assert result.target_ticks is None


def test_unpublished_internal_bar_cannot_be_skipped_to_complete_atr_warmup():
    first=Bar('X','H1',T,T+timedelta(hours=1),100,102,98,100)
    delayed=Bar('X','H1',T+timedelta(hours=1),T+timedelta(hours=2),100,102,98,100,
                available_at=T+timedelta(hours=5))
    latest=Bar('X','H1',T+timedelta(hours=2),T+timedelta(hours=3),100,102,98,100)
    result=plan('BUY',100,latest.end,'H1',(first,delayed,latest),(),(),S,I,
                StrategyPolicy(near_atr_period=2,target_profile='fixed3r'))
    assert result.details['near_ticks'] is None


@pytest.mark.parametrize('linked,expected',[(False,94),(True,79)])
def test_range_origin_requires_entry_episode_link_before_widening_stop(linked,expected):
    protected=pool('protected',80)
    target=pool('external',130,'HIGH')
    selected=rng('BUY',protected,target)
    local=Bar('X','H1',T,T+timedelta(hours=1),100,105,95,100)
    result=plan('BUY',100,local.end,'H1',(local,),(),(protected,target),S,I,
                StrategyPolicy(),ranges=(selected,),protection_bars=(local,),
                protection_range_ids=('r',) if linked else ())
    assert result.status=='ELIGIBLE'
    assert result.stop_ticks==expected
    protected_ids={row[0] for row in result.details['protected_objects']}
    assert ('protected' in protected_ids) is linked
    assert local.id in protected_ids
