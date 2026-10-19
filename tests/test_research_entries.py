import json

import pandas as pd
import pytest

from slk import research_replay as r, research_entries as e, research_discovery as d


def signal(buy=True):
    return {'side':'BUY' if buy else 'SELL','entry':1.,'stop':.9 if buy else 1.1,'tp1':1.2 if buy else .8}


def bars(n=48):
    return pd.DataFrame({'open':1.,'high':1.01,'low':.99,'close':1.},index=pd.date_range('2026-10-19T09:00Z',periods=n,freq='h'))


def test_fillbar_stop_wins_over_target():
    f=bars(); f.loc[f.index[0],['low','high']]=[.8,1.3]
    x=e.execution(signal(),f,f.index[0],f.index[-1]+pd.Timedelta(hours=1),0.,0.)
    assert x['exit']=='stop' and x['result_R']==pytest.approx(-1.) and x['ambiguous_bar']


def test_no_fillbar_profit_and_endpoint_censoring():
    f=bars(3);f.loc[f.index[0],'high']=1.3
    assert e.execution(signal(),f,f.index[0],f.index[-1]+pd.Timedelta(hours=1),0.,0.)['status']=='censored'
    f.loc[f.index[1],'high']=1.3
    x=e.execution(signal(),f,f.index[0],f.index[-1]+pd.Timedelta(hours=1),0.,0.)
    assert x['exit']=='target' and x['result_R']==pytest.approx(2.)


def test_sell_ask_stop_and_gap_loss():
    f=bars();f.loc[f.index[0],'high']=1.099
    x=e.execution(signal(False),f,f.index[0],f.index[-1]+pd.Timedelta(hours=1),.002,.001)
    assert x['exit']=='stop' and x['result_R']< -1
    f=bars();f.loc[f.index[0],['open','low']]=[.8,.79]
    x=e.execution(signal(),f,f.index[0],f.index[-1]+pd.Timedelta(hours=1),0.,0.)
    assert x['result_R']==pytest.approx(-2.)


def test_missing_hour_before_result_censored():
    f=bars().drop(bars().index[1]);f.loc[f.index[2],'high']=1.3
    assert e.execution(signal(),f,f.index[0],f.index[-1]+pd.Timedelta(hours=1),0.,0.)['status']=='censored'


def test_unfilled_orders_counted():
    f=bars(); f['low']=1.05;f['high']=1.1;f['open']=1.07;f['close']=1.07
    assert e.execution(signal(),f,f.index[0],f.index[-1]+pd.Timedelta(hours=1),0.,0.)['status']=='unfilled'


def test_screen_selects_using_training_only(tmp_path):
    c=r.connect(tmp_path/'ledger.sqlite');start=pd.Timestamp('2026-01-01T00:00Z');end=start+pd.Timedelta(days=20)
    for period in range(2):
        for i in range(60):
            when=start+pd.Timedelta(days=period*10,hours=i)
            young=i<30
            event={'pair':'EURUSD','observed_at':when.isoformat(),'row':{'side':'BUY','trend':'down'},
                   'story_age_hours':24 if young else 400}
            score=(1. if young else -1.) if period==0 else (-999. if young else 999.)
            obs={'status':'observed','horizon_end':(when+pd.Timedelta(hours=24)).isoformat(),'signed_move_vol':score}
            eid=f'{period}:{i}'
            with c:
                c.execute('INSERT INTO events VALUES (?,?)',(eid,json.dumps(event)))
                c.execute('INSERT INTO observations VALUES (?,?)',(eid,json.dumps(obs)))
                c.execute('INSERT INTO decisions VALUES (?,?,1)',(eid,'keep'))
    result=d.screen(c,start,end)
    assert result['selected_on_development']=='age_under_10_days'
    assert result['later_period']['mean_signed_move_vol']==-999.
    c.close()


def test_no_evidence_not_best_policy(tmp_path):
    c=r.connect(tmp_path/'ledger.sqlite')
    result=d.screen(c,pd.Timestamp('2026-01-01T00:00Z'),pd.Timestamp('2026-02-01T00:00Z'))
    assert result['status']=='insufficient_data' and result['selected_on_development'] is None
    c.close()


def test_pending_cancelled_on_observed_story_end():
    f=bars(); f['low']=1.05;f['high']=1.1;f['open']=1.07;f['close']=1.07
    x=e.execution(signal(),f,f.index[0],f.index[-1]+pd.Timedelta(hours=1),0.,0.,cancel_at=f.index[2])
    assert x['status']=='cancelled_before_fill'


def test_incomplete_setup_search_not_no_setup(tmp_path,monkeypatch):
    f=bars(4);known=f.index[0];c=r.connect(tmp_path/'ledger.sqlite')
    event={'kind':'CONFIRMED','pair':'EURUSD','observed_at':known.isoformat(),'story_key':'one',
           'story_definition':{'some':'fixture'},'configuration':{},'row':{'side':'BUY'}}
    with c:c.execute('INSERT INTO events VALUES (?,?)',('e',json.dumps(event)))
    monkeypatch.setattr(e,'find_entries',lambda *a,**kw:[{'status':'NO_SETUP'}])
    e.evaluate(c,f,f.index[-1]+pd.Timedelta(hours=1),10)
    values=[json.loads(x[0])['status'] for x in c.execute('SELECT payload FROM entry_trials')]
    assert values and set(values)=={'censored_setup_search'}
    c.close()


def test_story_end_prevents_later_setup_search(tmp_path,monkeypatch):
    f=bars(24);known=f.index[0];c=r.connect(tmp_path/'ledger.sqlite')
    event={'kind':'CONFIRMED','pair':'EURUSD','observed_at':known.isoformat(),'story_key':'one',
           'story_definition':{'some':'fixture'},'configuration':{},'row':{'side':'BUY'}}
    ended={'kind':'INVALIDATED','observed_at':known.isoformat(),'story_key':'one'}
    with c:
        c.execute('INSERT INTO events VALUES (?,?)',('e',json.dumps(event)))
        c.execute('INSERT INTO events VALUES (?,?)',('x',json.dumps(ended)))
    def forbidden(*a,**k):raise AssertionError('must not look for entries after story end')
    monkeypatch.setattr(e,'find_entries',forbidden)
    e.evaluate(c,f,f.index[-1]+pd.Timedelta(hours=1),10)
    assert {json.loads(x[0])['status'] for x in c.execute('SELECT payload FROM entry_trials')}=={'cancelled_before_setup'}
    c.close()


def test_actual_pattern_pending_without_future_candles():
    from tests.test_entry import scenario,story_row,H1ONLY
    from slk.story import DEFAULT as STORY_DEFAULT
    from slk.entry import DEFAULT as ENTRY_DEFAULT
    full=scenario(retest=True)
    prefix=full.iloc[:15]  # Pattern just closed, retest has not happened.
    story=story_row(full)
    cfg={**ENTRY_DEFAULT,**H1ONLY}
    result=e.find_entries('EURUSD',prefix,[story],cfg,STORY_DEFAULT,False)[0]
    assert result['status']=='PENDING'
    assert r.live._ts(result['created_time'])<=prefix.index[-1]+pd.Timedelta(hours=1)
    # Future data does not enter prefix detection.
    assert e.find_entries('EURUSD',full.iloc[:15],[story],cfg,STORY_DEFAULT,False)[0]['entry']==result['entry']


def test_buy_bid_touch_does_not_fill_ask_limit():
    from tests.test_entry import scenario,story_row,H1ONLY
    from slk.story import DEFAULT as STORY_DEFAULT
    from slk.entry import DEFAULT as ENTRY_DEFAULT
    original=scenario(retest=True);f=original.copy()
    f['open']=2.2-original.open;f['close']=2.2-original.close
    f['high']=2.2-original.low;f['low']=2.2-original.high
    story=story_row(f,side='BUY',level=1.,target=1.12)
    cfg={**ENTRY_DEFAULT,**H1ONLY,'entry_models':['continuation']}
    pending=e.find_entries('EURUSD',f.iloc[:15],[story],cfg,STORY_DEFAULT)[0]
    assert pending['status']=='PENDING'
    price=pending['entry'];prefix=f.iloc[:16].copy()
    prefix.loc[prefix.index[-1],['open','high','low','close']]=[price+.0002,price+.0005,price-.00005,price+.0002]
    assert e.find_entries('EURUSD',prefix,[story],cfg,STORY_DEFAULT)[0]['status']=='PENDING'
