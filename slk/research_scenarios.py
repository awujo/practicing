"""Finite, causal counterfactual studies around native engine events and entry decisions.

No trading or broker calls. H1 cannot resolve intrabar order; ambiguous outcomes remain flagged.
"""
import json
import math
import sqlite3
import time
from pathlib import Path

import pandas as pd
from .candles import resample
from .instruments import pip
from .research import digest, encoded
from .research_replay import close_time, gaps, utc
from .research_entries import execution

HORIZONS = (24, 72)
MAX_RECORDS = 12000
EXIT_VARIANTS = ('baseline', 'stop_1p5_risk', 'stop_H1_structure', 'stop_H2_structure',
                 'stop_H4_structure', 'target_1R', 'target_2R', 'target_3R',
                 'target_nearest_structure', 'target_origin_range', 'partial_then_breakeven',
                 'trail_closed_H1', 'spread_0p5_pips', 'spread_2_pips', 'slippage_0p5_pips')


def window(frame, known, hours, cutoff):
    end = known + pd.Timedelta(hours=hours)
    f = frame[(frame.index >= known) & (frame.index < end)]
    ok = end <= cutoff and not f.empty and f.index[-1]+pd.Timedelta(hours=1) == end
    if ok:
        ok = not gaps(f, known, end)
    return f, ok


def completed(frame, tf, known):
    """Resample only the available prefix; require the nominal close, not last input row."""
    f = frame[frame.index+pd.Timedelta(hours=1) <= known]
    if f.empty:
        return resample(f, tf)
    bars = resample(f, tf)
    bars['end'] = [close_time(t, tf) for t in bars.start]
    return bars[bars.end <= known]


def features(frame, event):
    known = utc(event['observed_at']); prefix = frame[frame.index+pd.Timedelta(hours=1) <= known]
    ranges = prefix.high-prefix.low
    recent = float(ranges.tail(24).mean()); normal = float(ranges.tail(480).mean())
    r = event['row']; side = r['side']; sign = 1 if side == 'BUY' else -1
    wat = known.tz_convert('Africa/Lagos')
    return {'story_age_hours': event.get('story_age_hours'), 'story_tf': r['story'],
            'side': side, 'origin_agrees': (r.get('trend') == ('up' if sign == 1 else 'down')) if r.get('trend') in ('up','down') else None,
            'higher_agrees': (r.get('htf_trend') == ('up' if sign == 1 else 'down')) if r.get('htf_trend') in ('up','down') else None,
            'wat_hour': wat.hour, 'weekday': wat.dayofweek,
            'volatility_ratio': recent/normal if normal > 0 else None,
            'distance_from_level_h1_range': sign*(float(prefix.close.iloc[-1])-r['level'])/recent if recent > 0 else None,
            'rule': r.get('rule'), 'level_kind': r.get('level_kind'),
            'context': 'prefix-only features; descriptive groups, not causal explanations'}


def path_after_stop(signal, result, frame, cutoff):
    if result.get('exit') != 'stop':
        return {'status': 'not_stopped'}
    known = utc(result['closed_at']); risk = abs(signal['entry']-signal['stop'])
    sign = 1 if signal['side'] == 'BUY' else -1
    stopped_level=result.get('active_stop',signal['stop'])
    stopped_r=sign*(stopped_level-signal['entry'])/risk
    out = {'observed_at': known.isoformat(), 'stop_bar_ambiguous': result.get('ambiguous_bar', False), 'horizons': {}}
    # Start AFTER the stop bar closes; no claim about ordering inside the stopped candle.
    for hours in HORIZONS:
        f, ok = window(frame, known, hours, cutoff)
        if not ok:
            out['horizons'][str(hours)] = {'status': 'censored'}; continue
        fav = f.high if sign == 1 else -f.low
        adverse = -f.low if sign == 1 else f.high
        recovered = fav >= sign*signal['entry']
        target = fav >= sign*signal['tp1']
        end_r = sign*(float(f.close.iloc[-1])-signal['entry'])/risk
        further = float((adverse+sign*stopped_level).max())/risk
        label = ('original_target_reached_after_stop' if target.any() else
                 'entry_recovered_after_stop' if recovered.any() else
                 'continued_against_trade' if end_r <= stopped_r-.5 else
                 'near_stopped_region' if abs(end_r-stopped_r) <= .5 else 'mixed_path')
        out['horizons'][str(hours)] = {'status': 'observed', 'classification': label,
            'entry_recovered': bool(recovered.any()), 'original_target_reached': bool(target.any()),
            'first_entry_recovery_bar_close': (recovered[recovered].index[0]+pd.Timedelta(hours=1)).isoformat() if recovered.any() else None,
            'endpoint_from_original_entry_R': end_r, 'further_adverse_from_stop_R': max(0., further)}
    return out


def signal_alternatives(signal, frame, known, pair, origin_tf='D'):
    """All candidate levels fixed from bars closed before the entry decision."""
    sign = 1 if signal['side'] == 'BUY' else -1
    entry = signal['entry']; risk = abs(entry-signal['stop']); buffer = pip(pair)*2
    out = {'baseline': dict(signal)}
    out['stop_1p5_risk'] = dict(signal, stop=entry-sign*risk*1.5)
    for tf in ('H1','H2','H4'):
        bars = completed(frame, tf, known).tail(5)
        if bars.empty: continue
        stop = float(bars.low.min())-buffer if sign == 1 else float(bars.high.max())+buffer
        if sign*(entry-stop) > 0:
            out['stop_'+tf+'_structure'] = dict(signal, stop=stop)
    for multiple in (1,2,3):
        out[f'target_{multiple}R'] = dict(signal, tp1=entry+sign*risk*multiple)
    h4 = completed(frame, 'H4', known).tail(60)
    values = h4.high if sign == 1 else h4.low
    pivots = ((values>=values.shift(1)) & (values>=values.shift(-1))) if sign==1 else ((values<=values.shift(1)) & (values<=values.shift(-1)))
    values=values[pivots]  # right neighbour is already closed at decision time
    candidates = values[sign*(values-entry) > pip(pair)]
    if not candidates.empty:
        target = float(candidates.min() if sign == 1 else candidates.max())
        out['target_nearest_structure'] = dict(signal, tp1=target)
    origin = completed(frame, origin_tf, known).tail(20)
    if not origin.empty:
        target = float(origin.high.max() if sign == 1 else origin.low.min())
        if sign*(target-entry) > 0:out['target_origin_range'] = dict(signal, tp1=target)
    return out


def managed_exit(signal, frame, known, cutoff, spread, slippage, policy, cancel_at=None):
    """Marketable limit semantics shared with execution; state updates only after H1 close.

    Half at 1R then breakeven, or a trailing three-closed-H1 structural stop.
    Stop takes priority over target; no same-fill-bar favourable fill.
    """
    sign = 1 if signal['side']=='BUY' else -1
    entry, stop, target = signal['entry'], signal['stop'], signal['tp1']
    risk = abs(entry-stop); filled = None; partial = False; realised = 0.; ambiguous = False
    expires = known+pd.Timedelta(hours=24)
    for t,b in frame[(frame.index>=known)&(frame.index<known+pd.Timedelta(hours=48))].iterrows():
        if t+pd.Timedelta(hours=1)>cutoff:break
        if gaps(frame,known,t+pd.Timedelta(hours=1)):return {'status':'censored'}
        if filled is None:
            if cancel_at is not None and t>=cancel_at:return {'status':'cancelled_before_fill'}
            if t>=expires:break
            if not (b.low+spread<=entry if sign==1 else b.high>=entry):continue
            filled=t
        elif t>=filled+pd.Timedelta(hours=24):break
        stopped = b.low<=stop if sign==1 else b.high+spread>=stop
        taken = b.high>=target if sign==1 else b.low+spread<=target
        first = b.high>=entry+risk if sign==1 else b.low+spread<=entry-risk
        if stopped:
            price=min(stop,float(b.open))-slippage if sign==1 else max(stop,float(b.open)+spread)+slippage
            return {'status':'closed','exit':'stop','result_R':realised+(0.5 if partial else 1)*sign*(price-entry)/risk,
                    'filled_at':filled.isoformat(),'closed_at':(t+pd.Timedelta(hours=1)).isoformat(),
                    'ambiguous_bar':bool(taken or (first and not partial)), 'partial_taken':partial, 'active_stop':stop, 'exit_price':price}
        if t>filled and taken:
            value=sign*(target-sign*slippage-entry)/risk
            if policy=='partial_then_breakeven' and not partial and sign*(target-entry)>=risk:
                realised=.5*(1-slippage/risk);partial=True
            return {'status':'closed','exit':'target','result_R':realised+(0.5 if partial else 1)*value,
                    'filled_at':filled.isoformat(),'closed_at':(t+pd.Timedelta(hours=1)).isoformat(),
                    'ambiguous_bar':ambiguous,'partial_taken':partial}
        if t==filled and (taken or first):ambiguous=True
        if policy=='partial_then_breakeven' and not partial and t>filled and first:
            realised=.5*(1-slippage/risk);partial=True;stop=entry
        if policy=='trail_closed_H1':
            trailing=frame[(frame.index<=t)&(frame.index>=filled)].tail(3)
            new=float(trailing.low.min()) if sign==1 else float(trailing.high.max())+spread
            stop=max(stop,new) if sign==1 else min(stop,new)
    if filled is None:
        _,ok=window(frame,known,24,cutoff)
        return {'status':'unfilled' if ok else 'censored'}
    end=filled+pd.Timedelta(hours=24);f,ok=window(frame,filled,24,cutoff)
    if not ok:return {'status':'censored'}
    price=float(f.close.iloc[-1])+(spread if sign==-1 else 0)-sign*slippage
    return {'status':'closed','exit':'time','result_R':realised+(0.5 if partial else 1)*sign*(price-entry)/risk,
            'filled_at':filled.isoformat(),'closed_at':end.isoformat(),'ambiguous_bar':ambiguous,'partial_taken':partial}


def reentry(signal, result, frame, cutoff, pair, opposite=False, cancel_at=None):
    if result.get('exit')!='stop':return {'status':'not_stopped'}
    known=utc(result['closed_at']); side=signal['side']
    if opposite:side='SELL' if side=='BUY' else 'BUY'
    sign=1 if side=='BUY' else -1
    # New setup requires a NEW completed H1 break after the stop was observable.
    search=frame[(frame.index>=known)&(frame.index<known+pd.Timedelta(hours=24))]
    for t,b in search.iterrows():
        decision=t+pd.Timedelta(hours=1)
        if decision>cutoff:break
        if cancel_at is not None and decision>=cancel_at:return {'status':'cancelled_before_setup'}
        prior=frame[frame.index<t].tail(3)
        if len(prior)<3 or gaps(frame,known,decision):return {'status':'censored'}
        level=float(prior.high.max() if sign==1 else prior.low.min())
        if sign*(float(b.close)-level)<=0:continue
        entry=float(b.close)+(pip(pair) if sign==1 else 0.)
        stop=float(prior.low.min())-2*pip(pair) if sign==1 else float(prior.high.max())+2*pip(pair)
        risk=sign*(entry-stop)
        if risk<=0:continue
        new={'side':side,'entry':entry,'stop':stop,'tp1':entry+sign*2*risk}
        outcome=execution(new,frame,decision,cutoff,pip(pair),.2*pip(pair),cancel_at)
        return dict(outcome,signal=new,observed_at=decision.isoformat(),rule='first new closed-H1 break of preceding three-bar range; limit retest, no market fill assumption')
    _,ok=window(frame,known,24,cutoff)
    return {'status':'no_new_setup' if ok else 'censored'}


def lifecycle_outcomes(event, frame, cutoff):
    known=utc(event['observed_at']);sign=1 if event['row']['side']=='BUY' else -1
    scale=event['volatility'];entry=event['reference_close'];out={}
    for hours in HORIZONS:
        f,ok=window(frame,known,hours,cutoff)
        if not ok:out[str(hours)]={'status':'censored'};continue
        fav=(float(f.high.max())-entry if sign==1 else entry-float(f.low.min()))/scale
        adverse=(entry-float(f.low.min()) if sign==1 else float(f.high.max())-entry)/scale
        out[str(hours)]={'status':'observed','endpoint_range':sign*(float(f.close.iloc[-1])-entry)/scale,
                         'favourable_range':max(0.,fav),'adverse_range':max(0.,adverse),
            'path_classification':('favourable_excursion_then_against' if fav>=1 and sign*(float(f.close.iloc[-1])-entry)<0 else
                                   'adverse_excursion_then_recovery' if adverse>=1 and sign*(float(f.close.iloc[-1])-entry)>0 else 'other_path')}
    return out


def delayed_confirmation(event, frame, cutoff):
    """Actual closed-origin confirmation after a native H4 external break; never imply intrabar validity."""
    r=event['row'];known=utc(event['observed_at']);tf=r['story'];sign=1 if r['side']=='BUY' else -1
    bars=completed(frame,tf,cutoff)
    later=bars[(bars.end>=known)&(bars.end<=known+pd.Timedelta(days=15 if tf=='D' else 70))]
    for _,b in later.iterrows():
        if gaps(frame,known,b.end):return {'status':'censored'}
        # Reject origin invalidation before a confirming body close.
        if sign*(float(b.close)-r['level'])<0:return {'status':'origin_invalidated','observed_at':b.end.isoformat()}
        if sign*(float(b.close)-r['point_b'])>0:
            when=b.end
            return {'status':'confirmed','observed_at':when.isoformat(),
                    'delay_hours':(when-known).total_seconds()/3600,
                    'outcomes':lifecycle_outcomes(dict(event,observed_at=when.isoformat(),reference_close=float(b.close)),frame,cutoff)}
    horizon=known+pd.Timedelta(days=15 if tf=='D' else 70)
    return {'status':'censored' if horizon>cutoff else 'no_origin_confirmation'}



def lifecycle_policies(event, observed_events):
    """Policy decisions at this event, based only on already observable native taps/confirmations."""
    r=event['row'];known=event['observed_at'];side=r['side'];after=r['status'] in ('TARGET_HIT','CANCELLED')
    past=[e for e in observed_events if e['observed_at']<=known and e['row']['story']==r['story']]
    taps=[e for e in past if e['kind']=='TAPPED' and utc(e['row']['tap_time'])>utc(r['tap_time'])]
    newer_same=any(e['row']['side']==side for e in taps)
    newer_opposite=any(e['row']['side']!=side for e in taps)
    latest={}
    for e in sorted(past,key=lambda x:x['observed_at']):latest[e['story_key']]=e
    confirmed=[e for e in latest.values() if e['row']['status']=='CONFIRMED' and not e['row'].get('no_trade') and not e['row'].get('line_end')
               and utc(e['row']['tap_time'])>utc(r['tap_time']) and e['row']['side']==side]
    eligible=event['kind'] in ('CONFIRMED','CONTINUATION') and not r.get('no_trade') and not r.get('line_end')
    eligible=eligible and r['status'] in ('CONFIRMED','TARGET_HIT','CANCELLED')
    age=event.get('story_age_hours',0)
    return {'keep':bool(eligible),'retire_at_target':bool(eligible and not after),
        'retire_on_new_same_direction_tap':bool(eligible and not newer_same),
        'retire_on_new_opposite_direction_tap':bool(eligible and not newer_opposite),
        'only_latest_tap_story':bool(eligible and not taps),
        'renew_after_target_with_new_origin_confirmation':bool(eligible and (not after or confirmed)),
        **{'age_'+str(days)+'_days':bool(eligible and age<=days*24) for days in (5,10,20,40)}}

def study(conn, frame, cutoff, out, seconds=180):
    """Sidecar ledger: original event/trial ledgers remain immutable."""
    begun=time.monotonic();out=Path(out);out.mkdir(parents=True,exist_ok=True)
    events={eid:json.loads(v) for eid,v in conn.execute('SELECT id,payload FROM events')}
    identity,manifest=conn.execute('SELECT identity,manifest FROM meta WHERE id=1').fetchone()
    scenario_manifest={'parent_identity':identity,'parent_manifest':json.loads(manifest),'outcome_cutoff':cutoff.isoformat(),
        'scenario_code_sha256':digest(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))), 'exit_variants':EXIT_VARIANTS,
        'horizons_hours':HORIZONS,'costs':'one-pip fixed spread, 0.2-pip slippage, zero commission',
        'execution':'H1 conservative; same-bar stop/target ambiguity flagged, no M5 evidence',
        'selection':'one-factor alternatives; not all Cartesian combinations or globally optimal',
        'reentry':'one new range-break limit setup per direction after observable stop, not recursive',
        'story_replacement':'native new Daily/Weekly taps and confirmations; no invented price-pattern grammar',
        'unsupported':['M5 execution without M5 data','causal market explanations','unbounded feature search']}
    db=sqlite3.connect(out/'ledger.sqlite');db.execute('PRAGMA max_page_count=1280')
    db.executescript('''CREATE TABLE IF NOT EXISTS meta(id INTEGER PRIMARY KEY,identity TEXT,manifest TEXT);
      CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,payload TEXT);
      CREATE TABLE IF NOT EXISTS observations(event_id TEXT PRIMARY KEY,payload TEXT);
      CREATE TABLE IF NOT EXISTS decisions(event_id TEXT,policy TEXT,accepted INTEGER);
      CREATE TABLE IF NOT EXISTS scenarios(id TEXT PRIMARY KEY,payload TEXT);''')
    sid=digest(encoded(scenario_manifest));old=db.execute('SELECT identity FROM meta').fetchone()
    if old and old[0]!=sid:db.close();raise ValueError('scenario identity mismatch')
    db.execute('INSERT OR IGNORE INTO meta VALUES(1,?,?)',(sid,encoded(scenario_manifest).decode()));db.commit()
    def exists(key):
        if time.monotonic()-begun>seconds:raise TimeoutError('scenario budget exhausted')
        return db.execute('SELECT 1 FROM scenarios WHERE id=?',(digest(encoded(key)),)).fetchone() is not None
    def write(key,value):
        if time.monotonic()-begun>seconds:raise TimeoutError('scenario budget exhausted')
        if db.execute('SELECT count(*) FROM scenarios').fetchone()[0]>=MAX_RECORDS:raise OverflowError('scenario record cap')
        rid=digest(encoded(key));db.execute('INSERT OR IGNORE INTO scenarios VALUES(?,?)',(rid,encoded(value).decode()));db.commit()
    status='complete'
    try:
        ordered=sorted(events.items(),key=lambda x:(x[1]['observed_at'],x[0]))
        for eid,event in ordered:
            if event['kind'] not in ('TAPPED','CONFIRMED','CONTINUATION','TARGET_HIT','LINE_END','INVALIDATED','EXTERNAL_BREAK_PENDING_ORIGIN'):continue
            if exists(['lifecycle',eid]):continue
            known=utc(event['observed_at']);r=event['row'];ctx=features(frame,event)
            # New taps can coexist with an old story. Compare explicitly, do not manufacture a new tap retrospectively.
            active=[x for _,x in ordered if x['pair']==event['pair'] and x['row']['story']==r['story']
                    and x['story_key']!=event['story_key'] and x['observed_at']<event['observed_at']
                    and x['kind'] in ('CONFIRMED','CONTINUATION','TARGET_HIT','LINE_END','INVALIDATED','ENDED_FLIP','CANCELLED')]
            latest={}
            for x in active:latest[x['story_key']]=x
            oldstories=[x for x in latest.values() if x['kind'] not in ('LINE_END','INVALIDATED','ENDED_FLIP','CANCELLED') and not x['row'].get('no_trade')]
            value={'family':'lifecycle','event_id':eid,'kind':event['kind'],'story_key':event['story_key'],
                'observed_at':event['observed_at'],'features':ctx,'outcomes':lifecycle_outcomes(event,frame,cutoff),'policies':lifecycle_policies(event,list(events.values())),
                'existing_other_stories':len(oldstories),'same_direction_other_stories':sum(x['row']['side']==r['side'] for x in oldstories)}
            if event['kind']=='EXTERNAL_BREAK_PENDING_ORIGIN':value['origin_confirmation']=delayed_confirmation(event,frame,cutoff)
            write(['lifecycle',eid],value)
        tables={x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'entry_trials' in tables:
            for eid,variant,payload in conn.execute('SELECT event_id,variant,payload FROM entry_trials ORDER BY event_id,variant'):
                base=json.loads(payload);event=events[eid]
                if not base.get('signal'):continue
                signal=base['signal'];known=utc(base['observed_at']);pair=event['pair']
                endings=[utc(x['observed_at']) for x in events.values() if x['story_key']==event['story_key']
                         and x['kind'] in ('TARGET_HIT','INVALIDATED','CANCELLED','ENDED_FLIP','LINE_END') and utc(x['observed_at'])>=known]
                cancel=min(endings) if endings else None
                alternatives=signal_alternatives(signal,frame,known,pair,event['row']['story'])
                for name,candidate in alternatives.items():
                    if exists(['entry',eid,variant,name]):continue
                    result=execution(candidate,frame,known,cutoff,pip(pair),.2*pip(pair),cancel)
                    value={'family':'entry_counterfactual','event_id':eid,'entry_variant':variant,'alternative':name,
                        'observed_at':known.isoformat(),'signal':candidate,'result':result,'features':features(frame,event),
                        'stop_risk_ratio_to_baseline':abs(candidate['entry']-candidate['stop'])/abs(signal['entry']-signal['stop']),
                        'post_stop':path_after_stop(candidate,result,frame,cutoff)}
                    if name=='baseline':
                        value['same_direction_reentry']=reentry(candidate,result,frame,cutoff,pair,cancel_at=cancel)
                        value['opposite_direction_setup']=reentry(candidate,result,frame,cutoff,pair,True,None)
                    write(['entry',eid,variant,name],value)
                for name,spread,slip in (('spread_0p5_pips',.5,.2),('spread_2_pips',2.,.2),('slippage_0p5_pips',1.,.5)):
                    if exists(['entry',eid,variant,name]):continue
                    result=execution(signal,frame,known,cutoff,pip(pair)*spread,pip(pair)*slip,cancel)
                    write(['entry',eid,variant,name],{'family':'entry_counterfactual','event_id':eid,'entry_variant':variant,
                        'alternative':name,'signal':signal,'observed_at':known.isoformat(),'result':result,
                        'costs':{'spread_pips':spread,'slippage_pips':slip,'commission':0},
                        'selection':'same baseline setup; execution-cost sensitivity, not cost-aware setup regeneration'})
                for name in ('partial_then_breakeven','trail_closed_H1'):
                    if exists(['entry',eid,variant,name]):continue
                    result=managed_exit(signal,frame,known,cutoff,pip(pair),.2*pip(pair),name,cancel)
                    write(['entry',eid,variant,name],{'family':'entry_counterfactual','event_id':eid,'entry_variant':variant,
                          'alternative':name,'signal':signal,'observed_at':known.isoformat(),'result':result,
                          'post_stop':path_after_stop(signal,result,frame,cutoff)})
    except (TimeoutError,OverflowError):status='budget_exhausted'
    except Exception:
        status='failed'
        raise
    finally:
        values=[json.loads(v) for v, in db.execute('SELECT payload FROM scenarios')]
        from collections import Counter
        summary={'status':status,'records':len(values),'families':dict(Counter(v['family'] for v in values)),
                 'manifest':scenario_manifest,'conclusion':'Descriptive counterfactuals; not independent trades or validated optimal rules.'}
        (out/'report.json').write_bytes(encoded(summary));db.close()
    return summary


def aggregate(root):
    """Bounded descriptive aggregate; no policy selected using observed outcomes."""
    from collections import defaultdict, Counter
    entry=defaultdict(list);entry_status=defaultdict(Counter);paths=defaultdict(Counter)
    policy=defaultdict(dict);context=defaultdict(dict);event_paths=defaultdict(list);timing=Counter();reentries=defaultdict(Counter);families=Counter();seen=set()
    for path in sorted(Path(root).rglob('scenarios/ledger.sqlite')):
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            _,manifest=db.execute('SELECT identity,manifest FROM meta WHERE id=1').fetchone()
            pair=json.loads(manifest)['parent_manifest']['pair']
            for rid,payload in db.execute('SELECT id,payload FROM scenarios'):
                v=json.loads(payload)
                unit=(pair,v['family'],v['event_id'],v.get('entry_variant'),v.get('alternative'))
                if unit in seen:continue
                seen.add(unit);families[v['family']]+=1
                if v['family']=='entry_counterfactual':
                    group=v['entry_variant']+' / '+v['alternative'];result=v['result']
                    entry_status[group][result['status']]+=1
                    if result['status']=='closed':entry[group].append(result['result_R'])
                    if v['alternative']=='baseline':
                        for h,p in v.get('post_stop',{}).get('horizons',{}).items():
                            paths[v['entry_variant']+' / '+h][p.get('classification',p['status'])]+=1
                        for k in ('same_direction_reentry','opposite_direction_setup'):
                            if k in v:reentries[v['entry_variant']+' / '+k][v[k]['status']]+=1
                else:
                    f=v['features']
                    for h,o in v['outcomes'].items():
                        if o['status']=='observed':event_paths[f['story_tf']+' / '+v['kind']+' / '+h].append(o)
                    if 'origin_confirmation' in v:timing[f['story_tf']+' / '+v['origin_confirmation']['status']]+=1
                    if v.get('policies',{}).get('keep'):
                        labels=['origin_agrees_'+str(f['origin_agrees']),'higher_agrees_'+str(f['higher_agrees']),
                            'wat_hour_bucket_'+str((f['wat_hour']//6)*6),
                            'age_'+('0_5d' if f['story_age_hours']<=120 else '5_10d' if f['story_age_hours']<=240 else '10_20d' if f['story_age_hours']<=480 else '20_40d' if f['story_age_hours']<=960 else 'over40d'),
                            'rule_'+str(f['rule']),'level_'+str(f['level_kind'])]
                        if f['volatility_ratio'] is not None:labels.append('volatility_'+('low' if f['volatility_ratio']<.75 else 'high' if f['volatility_ratio']>1.25 else 'normal'))
                        if f['distance_from_level_h1_range'] is not None:
                            distance=abs(f['distance_from_level_h1_range']);labels.append('distance_'+('under2' if distance<2 else '2_5' if distance<5 else '5_10' if distance<10 else 'over10'))
                        for h,o in v['outcomes'].items():
                            if o['status']!='observed':continue
                            for label in labels:
                                g=f['story_tf']+' / '+label+' / '+h;k=(pair,v['observed_at'],f['side'])
                                priority=(f.get('story_age_hours') or 0.,v['event_id']);old=context[g].get(k)
                                if old is None or priority<old[0]:context[g][k]=(priority,o['endpoint_range'])
                    for name,accepted in v.get('policies',{}).items():
                        if not accepted:continue
                        for horizon,o in v['outcomes'].items():
                            if o['status']!='observed':continue
                            f=v['features'];group=f['story_tf']+' / '+name+' / '+horizon
                            key=(pair,v['observed_at'],f['side'])
                            # Same candle/direction counted once, newest tap chosen by lowest age.
                            priority=(f.get('story_age_hours') or 0.,v['event_id'])
                            old=policy[group].get(key)
                            if old is None or priority<old[0]:policy[group][key]=(priority,o['endpoint_range'])
    return {'families':dict(families),
        'entries':{g:{'status_counts':dict(entry_status[g]),'closed':len(entry[g]),
            'mean_R':sum(entry[g])/len(entry[g]) if entry[g] else None} for g in sorted(entry_status)},
        'post_stop':{g:dict(v) for g,v in sorted(paths.items())},
        'origin_confirmation_statuses':dict(timing),
        'event_paths':{g:{'event_records':len(v),'mean_endpoint_range':sum(x['endpoint_range'] for x in v)/len(v),'path_counts':dict(Counter(x['path_classification'] for x in v))} for g,v in sorted(event_paths.items())},
        'context_groups':{g:{'distinct_pair_time_side':len(v),'mean_signed_h1_range':sum(x[1] for x in v.values())/len(v)} for g,v in sorted(context.items())},
        'reentry':{g:dict(v) for g,v in sorted(reentries.items())},
        'lifecycle_policies':{g:{'distinct_pair_time_side':len(v),
            'mean_signed_h1_range':sum(x[1] for x in v.values())/len(v) if v else None} for g,v in sorted(policy.items())},
        'warning':'Exploratory overlapping outcomes and matched counterfactuals; shared currency exposure. No winner or significance claim.'}
