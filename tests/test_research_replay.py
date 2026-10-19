"""Chronology and checkpoint tests for research, not profitability assertions."""
import json
import sqlite3

import pandas as pd
import pytest

from slk import research_replay as r
from slk.story import DEFAULT


def prices():
    idx = pd.date_range('2026-10-19T01:00Z', periods=8, freq='h')
    return pd.DataFrame({'open': 1., 'high': 1.2, 'low': .8, 'close': 1.1}, index=idx)


def row(status='CONFIRMED'):
    return dict(pair='EURUSD', story='D', tap_time=pd.Timestamp('2026-10-16T21:00Z'),
                confirm_time=pd.Timestamp('2026-10-18T21:00Z'), side='BUY', status=status,
                level=.9, point_b=1., target=1.5, cont_breaks=None)


def fake_state(pair, prefix, now, stories, cfg, memo):
    assert prefix.index[-1] + pd.Timedelta(hours=1) <= now
    return [row('TAPPED' if now < pd.Timestamp('2026-10-19T05:00Z') else 'CONFIRMED')]


def test_transaction_resume_and_prefix_invariance(tmp_path):
    f = prices(); begin = f.index[0]+pd.Timedelta(hours=1); end=f.index[-1]+pd.Timedelta(hours=1)
    # Confirmation on Oct19 D candle is not closed until21: no backdated confirmation event.
    def state(pair, prefix, now, stories, cfg, memo):
        x=row(); x['confirm_time']=pd.Timestamp('2026-10-18T21:00Z')
        x['status']='TAPPED'
        if now >= pd.Timestamp('2026-10-19T05:00Z'):
            x['cont_breaks']='1.00000@2026-10-19 01:00'
        return [x]
    c=r.connect(tmp_path/'a.sqlite')
    assert r.replay(f,'EURUSD',begin,end,c,'one',{},state_fn=state)=='complete'
    before=list(c.execute('select * from events')); n=c.execute('select completed from progress').fetchone()[0]
    assert len(before)==1
    r.replay(f,'EURUSD',begin,end,c,'one',{},state_fn=state)
    assert list(c.execute('select * from events'))==before
    assert c.execute('select completed from progress').fetchone()[0]==n
    with pytest.raises(ValueError,match='identity'):
        r.replay(f,'EURUSD',begin,end,c,'two',{},state_fn=state)
    c.close()
    short=r.connect(tmp_path/'b.sqlite')
    r.replay(f.iloc[:4],'EURUSD',begin,end,short,'short',{},state_fn=state)
    assert list(short.execute('select * from events'))==before
    short.close()


def test_rollback_replays_failed_cutoff(tmp_path):
    c=r.connect(tmp_path/'a.sqlite'); f=prices(); calls=[]
    def fail(pair,prefix,now,stories,cfg,memo):
        calls.append(now)
        if len(calls)==2: raise ValueError('injected')
        return []
    begin=f.index[0]+pd.Timedelta(hours=1);end=f.index[-1]+pd.Timedelta(hours=1)
    with pytest.raises(ValueError):r.replay(f,'EURUSD',begin,end,c,'same',{},state_fn=fail)
    assert c.execute('select completed from progress').fetchone()[0]==1
    r.replay(f,'EURUSD',begin,end,c,'same',{},state_fn=lambda *a:[])
    assert c.execute('select completed from progress').fetchone()[0]==8
    c.close()


def test_missing_hour_fails_closed(tmp_path):
    f=prices().drop(prices().index[2]);c=r.connect(tmp_path/'a.sqlite')
    assert r.replay(f,'EURUSD',f.index[0]+pd.Timedelta(hours=1), f.index[-1]+pd.Timedelta(hours=1),c,'x',{},state_fn=lambda *a:[])=='missing_market_hours'
    c.close()


def test_outcome_elapsed_horizon_and_censoring():
    f=prices(); e=dict(observed_at=f.index[0].isoformat(), reference_close=1.,volatility=.1,row={'side':'BUY'})
    assert r.outcome(e,f,f.index[-1])['status']=='censored'
    f=pd.DataFrame({'open':1.,'high':1.2,'low':.8,'close':1.1},index=pd.date_range(f.index[0],periods=24,freq='h'))
    end=f.index[-1]+pd.Timedelta(hours=1)
    assert r.outcome(e,f,end)['signed_move_vol']==pytest.approx(1.)
    assert r.outcome(e,f.drop(f.index[4]),end)['status']=='censored'


def test_policy_rules():
    e={'kind':'CONTINUATION','observed_at':'2026-10-19T09:00Z','story_key':'old', 'row':row('TARGET_HIT')}
    assert r.accepted(e,'keep',{})
    assert not r.accepted(e,'retire_at_target',{})
    assert not r.accepted(e,'close_margin_0p5_range',{})
    e['break_margin_vol']=.6
    assert r.accepted(e,'close_margin_0p5_range',{})
    e['row']['no_trade']=True
    assert not any(r.accepted(e,p,{}) for p in r.POLICIES)


@pytest.mark.parametrize('tf,start,expected',[('H4','2026-10-19T05:00Z','2026-10-19T09:00Z'),
    ('D','2026-10-18T21:00Z','2026-10-19T21:00Z'),('W','2026-10-18T21:00Z','2026-10-23T21:00Z'),
    ('H4','2026-11-01T05:00Z','2026-11-01T10:00Z')])
def test_actual_close(tf,start,expected):
    assert r.close_time(start,tf)==pd.Timestamp(expected)


def test_confirm_time_is_already_a_close():
    now=pd.Timestamp('2026-10-19T21:00Z'); x=row();x['confirm_time']=now
    old=row('TAPPED')
    events=r.extract([x],{r.key(old):old},now)
    assert events[0]['kind']=='CONFIRMED'
    assert events[0]['occurred_at']==now.isoformat()


def test_fresh_story_candidate_suppresses_old_after_target():
    old={'kind':'CONTINUATION','story_key':'old','observed_at':'2026-10-19T09:00Z','row':row('TARGET_HIT')}
    context={'latest_confirmed':'fresh','latest_side':'BUY'}
    assert not r.accepted(old,'fresh_story',context)
    fresh={'kind':'CONFIRMED','story_key':'fresh','observed_at':'2026-10-19T09:00Z','row':row()}
    assert r.accepted(fresh,'fresh_story',context)
    fresh['row']['no_trade']=True
    assert not r.accepted(fresh,'fresh_story',context)


def test_real_engine_memo_equality_and_future_prefix():
    from tests.test_engine import walk
    from slk import live
    # Use no monthly/HTF filter for this minimal fixture; full research records actual code defaults.
    frame=walk(24*100);cutoff=frame.index[-1]+pd.Timedelta(hours=1)
    cfg={**DEFAULT,'use_monthly':False,'mw_conflict_filter':False,'htf_filter':False}
    stories=live.state_stories(['D'],cfg);memo={}
    one=r.clean(live.pair_state('EURUSD',frame,cutoff,stories,cfg,memo))
    two=r.clean(live.pair_state('EURUSD',frame,cutoff,stories,cfg,{}))
    assert one==two
    appended=frame.copy(); appended.index=appended.index+pd.Timedelta(days=200)
    both=pd.concat([frame,appended]);prefix=both[both.index+pd.Timedelta(hours=1)<=cutoff]
    assert r.clean(live.pair_state('EURUSD',prefix,cutoff,stories,cfg,{}))==one


def test_real_confirmed_or_ended_event_uses_actual_close():
    from tests.test_engine import walk
    from slk import live
    f=walk(24*100);cfg={**DEFAULT,'use_monthly':False,'mw_conflict_filter':False,'htf_filter':False}
    stories=live.state_stories(['D'],cfg)
    final=live.pair_state('EURUSD',f,f.index[-1]+pd.Timedelta(hours=1),stories,cfg,{})
    candidates=[x for x in final if x['story']=='D' and x.get('confirm_time')]
    assert candidates
    now=live._ts(candidates[0]['confirm_time'])
    prefix=f[f.index+pd.Timedelta(hours=1)<=now]
    rows=live.pair_state('EURUSD',prefix,now,stories,cfg,{})
    events=r.extract(rows,{},now)
    assert any(e['kind']=='CONFIRMED' and e['occurred_at']==now.isoformat() for e in events)


def test_daily_and_weekly_freshness_are_independent(tmp_path):
    f=prices();begin=f.index[0]+pd.Timedelta(hours=1);end=f.index[-1]+pd.Timedelta(hours=1)
    def state(pair,prefix,now,stories,cfg,memo):
        out=[]
        for tf in ('D','W'):
            x=row('TAPPED' if now==begin else 'CONFIRMED');x['story']=tf
            x['confirm_time']=None if now==begin else now
            out.append(x)
        return out
    c=r.connect(tmp_path/'ledger.sqlite')
    r.replay(f,'EURUSD',begin,end,c,'identity',{},state_fn=state,origins=('D','W'))
    assert c.execute("select count(*) from decisions where policy='fresh_story' and accepted=1").fetchone()[0]==2


def test_gap_skipping_is_explicit_and_rebootstraps(tmp_path):
    f=prices().drop(prices().index[2]);begin=f.index[0]+pd.Timedelta(hours=1);end=f.index[-1]+pd.Timedelta(hours=1)
    c=r.connect(tmp_path/'ledger.sqlite')
    status=r.replay(f,'EURUSD',begin,end,c,'identity',{},state_fn=fake_state,skip_recent_gaps=True)
    assert status=='complete'
    assert c.execute('select count(*) from skips').fetchone()[0]>0
