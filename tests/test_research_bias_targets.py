from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from slk import research_bias_targets as b
from slk.story import DEFAULT


def frame():
    return pd.DataFrame({'open':1.,'high':1.01,'low':.99,'close':1.},
        index=pd.date_range('2026-10-19T01:00Z',periods=12,freq='h'))


def event():
    return dict(kind='CONFIRMED',story_key='s',observed_at='2026-10-19T02:00Z',
                row=dict(side='BUY',level=.8,target=1.1),story_definition={})


class Select:
    def __init__(self):
        self.calls=[];self.ctx=SimpleNamespace(o_end=[],O={'close':[]})
    def choose(self,known,side,reference):
        self.calls.append((known,reference))
        return {'price':reference+.1,'selected_at':known.isoformat(),'source':'test'}


def test_successive_targets_are_chosen_only_after_previous_hit():
    f=frame();f.loc[f.index[1],'high']=1.15;f.loc[f.index[2],'high']=1.3
    selector=Select();r=b.measure_story(event(),[],f,f.index[-1]+pd.Timedelta(hours=1),selector,'after_target_touch',max_stage=3)
    assert [x['status'] for x in r]==['reached','reached','unresolved_at_window_end']
    assert selector.calls[0][0]==pd.Timestamp('2026-10-19T03:00Z')
    assert selector.calls[0][1]==1.15 # full completed hit bar's high excluded from next target
    assert r[1]['target']>1.15


def test_waits_for_new_closed_continuation_before_next_target():
    f=frame();f.loc[f.index[1],'high']=1.15
    selector=Select();e=event();cont=dict(kind='CONTINUATION',story_key='s',observed_at='2026-10-19T05:00Z')
    r=b.measure_story(e,[cont],f,f.index[-1]+pd.Timedelta(hours=1),selector,'after_continuation_close',max_stage=2)
    assert r[1]['selected_at']=='2026-10-19T05:00:00+00:00'
    assert selector.calls[0][0]==pd.Timestamp(cont['observed_at'])


def test_no_continuation_does_not_count_as_failed_target():
    f=frame();f.loc[f.index[1],'high']=1.15
    r=b.measure_story(event(),[],f,f.index[-1]+pd.Timedelta(hours=1),Select(),'after_continuation_close')
    assert r[1]['status']=='unresolved_waiting_continuation' and 'target' not in r[1]


def test_same_hour_target_and_end_is_ambiguous():
    f=frame();f.loc[f.index[1],'high']=1.15
    r=b.walk(f,f.index[1],1.1,'BUY',f.index[-1],barrier=f.index[2])
    assert r['status']=='target_and_end_same_bar'


def test_missing_hour_cannot_be_assumed_to_miss_target():
    f=frame().drop(frame().index[2]);f.loc[f.index[2],'high']=1.3
    assert b.walk(f,frame().index[1],1.1,'BUY',f.index[-1])['status']=='censored_gap'


def test_target_already_taken_at_confirmation_is_separate():
    f=frame();e=event();f.loc[f.index[0],'high']=1.15
    assert b.measure_story(e,[],f,f.index[-1],Select(),'after_target_touch')[0]['status']=='already_taken_at_confirmation'


@pytest.mark.parametrize('origin',['D','W'])
def test_native_target_selector_is_future_invariant(origin):
    from tests.test_engine import walk
    f=walk(24*150);known=f.index[24*100]+pd.Timedelta(hours=1);prefix=f[f.index+pd.Timedelta(hours=1)<=known]
    changed=f.copy();changed.loc[changed.index+pd.Timedelta(hours=1)>known,['open','high','low','close']]=[5.,6.,4.,5.]
    cfg={**DEFAULT,'use_monthly':True}
    a=b.Selector('EURUSD',prefix,origin,cfg);c=b.Selector('EURUSD',changed,origin,cfg)
    actual=[]
    for side,ref in [('BUY',.1),('SELL',10.)]:
        x=a.choose(known,side,ref);y=c.choose(known,side,ref)
        assert x==y;actual.append(x)
    assert any(x is not None for x in actual)


def test_erl_taken_flag_does_not_discard_replaced_forward_target():
    f=frame();e=event();e['story_definition']['erl_taken']=True
    r=b.measure_story(e,[],f,f.index[-1],Select(),'after_target_touch')
    assert r[0]['status']=='unresolved_at_window_end'
