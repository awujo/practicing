"""Prefix-only entry-policy experiments; conservative H1 execution, no portfolio claims."""
import json
import time

import pandas as pd
from . import live
from .entry import DEFAULT
from . import entry as engine
import numpy as np
from .instruments import pip
from .research import encoded
from .research_replay import gaps, close_time, utc

VARIANTS = {'H4_zone':('H4','zone'), 'H2_zone':('H2','zone'),
            'H1_zone':('H1','zone'), 'H1_rejection':('H1','rejection')}



def find_entries(pair, prefix, stories, cfg, story_cfg, sim=False):
    """Research adapter: existing patterns, explicit prospective search horizon.

    The full-history entry finder treats the end of its input as a terminal horizon;
    that is not suitable for observing still-pending orders in a prefix replay.
    """
    config={**DEFAULT,**cfg,'spread_pips':1.,'story_cfg':story_cfg}
    px=engine._Pair(pair,prefix,config)
    now=prefix.index[-1]+pd.Timedelta(hours=1)
    out=[]
    for story in stories:
        if pair in config['avoid_pairs']:
            out.append({'status':'SKIPPED'});continue
        sell=story['side']=='SELL'
        # The caller enforces observed lifecycle termination and the fixed 24-hour search cap.
        horizon=engine._t(now+pd.Timedelta(hours=24))
        candidates=[]
        for tf in config['entry_tfs'][story.get('story','D')]:
            for model in config.get('entry_models',engine.MODELS):
                found,_=(engine._candidates(px,tf,story,sell,engine._t(story.get('breakout_time') or story['confirm_time']),engine._t(story['confirm_time']),horizon)
                         if model=='continuation' else engine._qmr_candidates(px,tf,story,sell,engine._t(story['confirm_time']),horizon))
                candidates.extend(found)
        if not candidates:
            out.append({'status':'NO_SETUP'});continue
        chosen,fill=engine._walk(px,candidates,sell,horizon)
        pending=fill is None and min(chosen['expires'],horizon)>px.h1['end'][-1]
        out.append({**chosen,'side':story['side'],'status':'PENDING' if pending else 'TRIGGERED' if fill is not None else 'MISSED',
                    'created_time':engine._s(chosen['active'])})
    return out


def execution(signal, frame, known, cutoff, spread, slippage, cancel_at=None):
    """Limit order active after decision; fill bar can stop but cannot take profit."""
    buy=signal['side']=='BUY';entry=signal['entry'];stop=signal['stop'];target=signal['tp1']
    risk=abs(entry-stop)
    if risk<=0 or (buy and not stop<entry<target) or (not buy and not target<entry<stop):
        raise ValueError('invalid entry/stop/target geometry')
    expires=known+pd.Timedelta(hours=24);filled=None; ambiguous=False
    for t,b in frame[(frame.index>=known)&(frame.index<known+pd.Timedelta(hours=48))].iterrows():
        if t+pd.Timedelta(hours=1)>cutoff:break
        if gaps(frame,known,t+pd.Timedelta(hours=1)):
            return {'status':'censored','reason':'missing_market_hours'}
        if filled is None:
            if cancel_at is not None and t>=cancel_at:return {'status':'cancelled_before_fill'}
            if t>=expires:break
            hit=b.low+spread<=entry if buy else b.high>=entry
            if not hit:continue
            filled=t
        elif t>=filled+pd.Timedelta(hours=24):break
        stopped=b.low<=stop if buy else b.high+spread>=stop
        taken=b.high>=target if buy else b.low+spread<=target
        if stopped:
            # Conservative gap stop at adverse opening quote, plus slippage.
            price=min(stop,float(b.open)) - slippage if buy else max(stop,float(b.open)+spread)+slippage
            value=((price-entry) if buy else (entry-price))/risk
            return {'status':'closed','result_R':value,'filled_at':filled.isoformat(),'closed_at':(t+pd.Timedelta(hours=1)).isoformat(),
                    'exit':'stop','ambiguous_bar':bool(taken),'execution':'H1 conservative; assumed fixed spread/slippage; zero commission'}
        if taken and t>filled:
            price=target-slippage if buy else target+slippage
            return {'status':'closed','result_R':((price-entry) if buy else (entry-price))/risk,
                    'filled_at':filled.isoformat(),'closed_at':(t+pd.Timedelta(hours=1)).isoformat(),
                    'exit':'target','ambiguous_bar':ambiguous,'execution':'H1 conservative; assumed fixed spread/slippage; zero commission'}
        if taken and t==filled:ambiguous=True
    end=(filled+pd.Timedelta(hours=24)) if filled is not None else expires
    window=frame[(frame.index>=known)&(frame.index<end)]
    if end>cutoff or window.empty or window.index[-1]+pd.Timedelta(hours=1)!=end or gaps(window,known,end):
        return {'status':'censored','filled_at':filled.isoformat() if filled is not None else None}
    if filled is None:return {'status':'unfilled'}
    quote=float(window.close.iloc[-1]) if buy else float(window.close.iloc[-1])+spread
    price=quote-slippage if buy else quote+slippage
    return {'status':'closed','result_R':((price-entry) if buy else (entry-price))/risk,'exit':'time',
            'filled_at':filled.isoformat(),'closed_at':end.isoformat(),'ambiguous_bar':ambiguous,
            'execution':'H1 conservative; assumed fixed spread/slippage; zero commission'}


def evaluate(conn, frame, cutoff, seconds, cap=12):
    if not 1<=cap<=128:raise ValueError("entry cap must be 1..128")
    begun=time.monotonic()
    conn.execute('CREATE TABLE IF NOT EXISTS entry_trials (event_id TEXT, variant TEXT, payload TEXT, PRIMARY KEY(event_id,variant))')
    signals=[(i,json.loads(v)) for i,v in conn.execute('SELECT id,payload FROM events ORDER BY json_extract(payload,\'$.observed_at\'),id')
             if json.loads(v)['kind']=='CONFIRMED' and json.loads(v).get('story_definition') and not json.loads(v)['row'].get('no_trade') and not json.loads(v).get('already_ended_at_observation')]
    selected=signals[:cap]  # Explicit chronological cap; report unevaluated remainder.
    for eid,event in selected:
        known=utc(event['observed_at']); pair=event['pair'];raw=event['story_definition']
        lifecycle=[json.loads(payload) for payload, in conn.execute('SELECT payload FROM events')]
        endings=[utc(x['observed_at']) for x in lifecycle if x['story_key']==event['story_key']
                 and x['kind'] in ('TARGET_HIT','INVALIDATED','CANCELLED','ENDED_FLIP','LINE_END')
                 and utc(x['observed_at'])>=known]
        cancel_at=min(endings) if endings else None
        for variant,(tf,stop_at) in VARIANTS.items():
            if conn.execute('SELECT 1 FROM entry_trials WHERE event_id=? AND variant=?',(eid,variant)).fetchone():continue
            if time.monotonic()-begun>=seconds:return {'status':'budget_exhausted','eligible_confirmations':len(signals),'cap':cap}
            search_end=known+pd.Timedelta(hours=24)
            result={'status':'censored_setup_search'} if cutoff<search_end or gaps(frame,known,min(search_end,cutoff)) else {'status':'no_pending_setup_in_24h'}
            # An entry must be observable while pending. Backdated already-filled setups are never admitted.
            for decision in pd.date_range(known, min(known+pd.Timedelta(hours=24),cutoff),freq='h'):
                if cancel_at is not None and decision>=cancel_at:
                    result={'status':'cancelled_before_setup'};break
                if time.monotonic()-begun>=seconds:return {'status':'budget_exhausted','eligible_confirmations':len(signals),'cap':cap}
                if close_time(decision-pd.Timedelta(hours=1),tf)!=decision:continue
                prefix=frame[(frame.index>=known-pd.Timedelta(days=90))&(frame.index+pd.Timedelta(hours=1)<=decision)]
                if prefix.empty or gaps(prefix,max(known-pd.Timedelta(days=1),prefix.index[0]),decision):continue
                # decision is explicitly a tf close; no forming bin is admitted.
                cfg={**DEFAULT,'entry_tfs':{raw.get('story','D'):(tf,)},'stop_at':stop_at,'alignment':'off'}
                found=find_entries(pair,prefix,[raw],cfg,story_cfg=event['configuration'],sim=False)[0]
                if found.get('status')!='PENDING':continue
                formed=live._ts(found['created_time'])
                if not known<=formed<=decision:continue
                signal={k:found[k] for k in ('entry','stop','tp1','side')}
                result=execution(signal,frame,decision,cutoff,spread=pip(pair)*1.,slippage=pip(pair)*.2,cancel_at=cancel_at)
                result.update(signal=signal,observed_at=decision.isoformat(),entry_timeframe=tf,
                              assumptions={'spread_pips':1.,'slippage_pips':.2,'commission':0,'alignment':'off','holding_hours':24,'pending_hours':24,'cancellation':'pending only, at first observed H4 lifecycle end'})
                break
            with conn:conn.execute('INSERT INTO entry_trials VALUES (?,?,?)',(eid,variant,encoded(result).decode()))
    counts={}
    for variant in VARIANTS:
        values=[json.loads(v) for v, in conn.execute('SELECT payload FROM entry_trials WHERE variant=?',(variant,))]
        closed=[v['result_R'] for v in values if v['status']=='closed']
        counts[variant]={'trials':len(values),'closed':len(closed),'censored':sum(v['status'].startswith('censored') for v in values),
                         'mean_R':sum(closed)/len(closed) if closed else None}
    return {'status':'complete' if len(signals)<=cap else 'confirmation_cap_reached','eligible_confirmations':len(signals),
            'evaluated_confirmations':len(selected),'variants':counts,
            'conclusion':'Experimental pending-entry comparison. Not live-policy replication, portfolio performance or validated edge.'}
