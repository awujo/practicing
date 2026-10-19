import json
import sqlite3
import pandas as pd
import pytest
from slk import research_scenarios as s
from slk.research_replay import connect


def bars(n=120):
    return pd.DataFrame({'open':1.,'high':1.01,'low':.99,'close':1.},
        index=pd.date_range('2026-10-19T01:00Z',periods=n,freq='h'))


def signal():return dict(side='BUY',entry=1.,stop=.9,tp1=1.2)


def event(kind='CONTINUATION',when='2026-10-20T01:00Z',tap='2026-10-01T21:00Z',side='BUY'):
    return dict(pair='EURUSD',kind=kind,story_key='EURUSD|D|'+tap,observed_at=when,volatility=.02,
        reference_close=1.,story_age_hours=300.,row=dict(story='D',side=side,level=.8,point_b=.95,
        trend='up',htf_trend='up',tap_time=tap,status='TARGET_HIT'))


def test_future_changes_cannot_change_structural_candidates():
    f=bars();known=f.index[24];a=s.signal_alternatives(signal(),f,known,'EURUSD')
    changed=f.copy();changed.loc[changed.index>=known,['high','close']]=2.
    assert a==s.signal_alternatives(signal(),changed,known,'EURUSD')


def test_forming_h4_is_not_a_structural_bar():
    f=bars(6);known=f.index[2]+pd.Timedelta(hours=1)
    assert s.completed(f,'H4',known).empty


def test_post_stop_excludes_stop_bar_and_requires_complete_horizon():
    f=bars(100);f.loc[f.index[0],'high']=1.5
    f.loc[f.index[1]:,'high']=1.05
    stopped=dict(exit='stop',closed_at=(f.index[0]+pd.Timedelta(hours=1)).isoformat(),ambiguous_bar=True)
    out=s.path_after_stop(signal(),stopped,f,f.index[-1]+pd.Timedelta(hours=1))
    assert out['horizons']['24']['entry_recovered']
    assert not out['horizons']['24']['original_target_reached']
    assert out['stop_bar_ambiguous']
    assert s.path_after_stop(signal(),stopped,f,f.index[12])['horizons']['24']['status']=='censored'


def test_stop_then_further_opposite_classification():
    f=bars();f.loc[:,['open','high','low','close']]=[.8,.85,.7,.75]
    result=s.path_after_stop(signal(),dict(exit='stop',closed_at=f.index[0].isoformat()),f,f.index[-1]+pd.Timedelta(hours=1))
    assert result['horizons']['24']['classification']=='continued_against_trade'


def test_partial_breakeven_activates_next_bar_only():
    f=bars(60);known=f.index[0]
    f.loc[f.index[1],['high','low']]=[1.15,.95] # partial at 1R; not allowed retroactive BE stop
    f.loc[f.index[2],'low']=.99
    r=s.managed_exit(signal(),f,known,f.index[-1]+pd.Timedelta(hours=1),0,0,'partial_then_breakeven')
    assert r['partial_taken'] and r['exit']=='stop' and r['result_R']==pytest.approx(.5)
    assert r['closed_at']==(f.index[2]+pd.Timedelta(hours=1)).isoformat()


def test_managed_same_bar_stop_has_priority():
    f=bars();f.loc[f.index[0],['low','high']]=[.8,1.3]
    r=s.managed_exit(signal(),f,f.index[0],f.index[-1]+pd.Timedelta(hours=1),0,0,'partial_then_breakeven')
    assert r['result_R']==pytest.approx(-1) and r['ambiguous_bar']


def test_reentry_cannot_fill_during_observed_setup_bar():
    f=bars();known=f.index[5]
    f.loc[known,['high','close']]=[1.1,1.05]
    stopped=dict(exit='stop',closed_at=known.isoformat())
    out=s.reentry(signal(),stopped,f,f.index[-1]+pd.Timedelta(hours=1),'EURUSD')
    assert out['observed_at']==(known+pd.Timedelta(hours=1)).isoformat()
    assert pd.Timestamp(out['filled_at'])>=pd.Timestamp(out['observed_at'])


def test_future_tap_cannot_retire_a_story():
    e=event();future=event('TAPPED','2026-10-21T01:00Z','2026-10-19T21:00Z')
    assert s.lifecycle_policies(e,[future])['only_latest_tap_story']
    future['observed_at']='2026-10-20T00:00Z'
    assert not s.lifecycle_policies(e,[future])['only_latest_tap_story']
    assert not s.lifecycle_policies(e,[future])['renew_after_target_with_new_origin_confirmation']
    future['kind']='CONFIRMED';future['row']['status']='CONFIRMED'
    assert s.lifecycle_policies(e,[future])['renew_after_target_with_new_origin_confirmation']


def test_short_stop_paths_are_symmetric():
    f=bars(100);buy=s.path_after_stop(signal(),dict(exit='stop',closed_at=f.index[0].isoformat()),f,f.index[-1]+pd.Timedelta(hours=1))
    short=dict(side='SELL',entry=1.,stop=1.1,tp1=.8)
    sell=s.path_after_stop(short,dict(exit='stop',closed_at=f.index[0].isoformat()),f,f.index[-1]+pd.Timedelta(hours=1))
    assert buy['horizons']['24']['entry_recovered']==sell['horizons']['24']['entry_recovered']


def test_sidecar_is_idempotent_and_preserves_parent(tmp_path):
    f=bars();c=connect(tmp_path/'source.sqlite');e=event('TAPPED')
    c.execute('insert into meta values(1,?,?)',('parent','{}'));c.execute('insert into events values(?,?)',('e',json.dumps(e)));c.commit()
    out=tmp_path/'scenario';r=s.study(c,f,f.index[-1]+pd.Timedelta(hours=1),out)
    assert r['records']==1
    assert s.study(c,f,f.index[-1]+pd.Timedelta(hours=1),out)['records']==1
    assert c.execute('select count(*) from events').fetchone()[0]==1
    assert sqlite3.connect(out/'ledger.sqlite').execute('select count(*) from scenarios').fetchone()[0]==1


def test_partial_same_bar_one_R_and_target_uses_half_sizes():
    f=bars(60);f.loc[f.index[1],'high']=1.25
    r=s.managed_exit(signal(),f,f.index[0],f.index[-1]+pd.Timedelta(hours=1),0,0,'partial_then_breakeven')
    assert r['result_R']==pytest.approx(1.5) and r['partial_taken']


def test_renewal_does_not_survive_new_story_invalidation():
    e=event();new=event('CONFIRMED','2026-10-20T00:00Z','2026-10-19T21:00Z')
    new['row']['status']='CONFIRMED'
    assert s.lifecycle_policies(e,[new])['renew_after_target_with_new_origin_confirmation']
    ended=json.loads(json.dumps(new));ended.update(kind='INVALIDATED',observed_at='2026-10-20T00:30Z');ended['row']['status']='INVALIDATED'
    assert not s.lifecycle_policies(e,[new,ended])['renew_after_target_with_new_origin_confirmation']


def test_managed_stop_path_uses_actual_breakeven_level():
    f=bars(100);f.loc[:,['open','high','low','close']]=[.95,.99,.9,.95]
    r=s.path_after_stop(signal(),dict(exit='stop',closed_at=f.index[0].isoformat(),active_stop=1.),f,f.index[-1]+pd.Timedelta(hours=1))
    assert r['horizons']['24']['further_adverse_from_stop_R']==pytest.approx(1.)


def test_resumed_lifecycle_skips_completed_evaluation(tmp_path,monkeypatch):
    f=bars();c=connect(tmp_path/'source.sqlite');e=event('TAPPED')
    c.execute('insert into meta values(1,?,?)',('parent','{}'));c.execute('insert into events values(?,?)',('e',json.dumps(e)));c.commit()
    out=tmp_path/'scenario';s.study(c,f,f.index[-1]+pd.Timedelta(hours=1),out)
    def fail(*a):raise AssertionError('completed row recomputed')
    monkeypatch.setattr(s,'features',fail)
    assert s.study(c,f,f.index[-1]+pd.Timedelta(hours=1),out)['status']=='complete'


def test_unexpected_error_does_not_write_complete_report(tmp_path,monkeypatch):
    f=bars();c=connect(tmp_path/'source.sqlite');c.execute('insert into meta values(1,?,?)',('parent','{}'))
    c.execute('insert into events values(?,?)',('e',json.dumps(event('TAPPED'))));c.commit()
    def fail(*a):raise ValueError('test failure')
    monkeypatch.setattr(s,'features',fail)
    with pytest.raises(ValueError):s.study(c,f,f.index[-1]+pd.Timedelta(hours=1),tmp_path/'scenario')
    assert json.loads((tmp_path/'scenario/report.json').read_text())['status']=='failed'


def test_sidecar_different_outcome_cutoff_requires_new_identity(tmp_path):
    f=bars();c=connect(tmp_path/'source.sqlite');c.execute('insert into meta values(1,?,?)',('parent','{}'));c.commit()
    s.study(c,f,f.index[-1]+pd.Timedelta(hours=1),tmp_path/'scenario')
    with pytest.raises(ValueError,match='identity mismatch'):
        s.study(c,f,f.index[-1],tmp_path/'scenario')


def test_automatic_aggregate_preserves_policy_units(tmp_path):
    f=bars();c=connect(tmp_path/'source.sqlite');e=event();e['row']['status']='CONFIRMED'
    c.execute('insert into meta values(1,?,?)',('parent',json.dumps({'pair':'EURUSD'})))
    c.execute('insert into events values(?,?)',('e',json.dumps(e)));c.commit()
    s.study(c,f,f.index[-1]+pd.Timedelta(hours=1),tmp_path/'scenarios')
    result=s.aggregate(tmp_path)
    assert result['families']['lifecycle']==1
    assert result['lifecycle_policies']['D / keep / 24']['distinct_pair_time_side']==1
    assert result['context_groups']
