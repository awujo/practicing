"""Measure frozen successive bias targets, not entry TP1. Offline research only."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
from .research import read_input, digest, encoded
from .research_replay import close_time, gaps, utc
from .story import _Ctx

MAX_STAGE=5
MODES=('after_target_touch','after_continuation_close')


class Selector:
    """Native ERL-first target chooser; all availability indexes are as-of time.

    The native backtest context is built once. Swing known-at, level birth/first-event,
    and nominal candle closes restrict every target query; future fields are never used.
    """
    def __init__(self,pair,frame,origin,cfg):
        idx=pd.date_range(frame.index[0],frame.index[-1]+pd.Timedelta(hours=1),freq='h',inclusive='left')
        ny=idx.tz_convert('America/New_York');dow=ny.dayofweek;hour=ny.hour
        expected=~((dow==5)|((dow==4)&(hour>=17))|((dow==6)&(hour<17)))
        self.missing=idx[expected].difference(frame.index).asi8
        self.ctx=_Ctx(pair,frame,origin,cfg)
        c=self.ctx
        c.o_end=np.array([close_time(t,origin) for t in c.o_start],dtype=object)
        c.lv.end=c.o_end.copy()
        for tf,levels in c.higher:
            levels.end=np.array([close_time(t,tf) for t in levels.start],dtype=object)

    def has_gap(self,start,end):
        return np.searchsorted(self.missing,utc(end).value,'left')>np.searchsorted(self.missing,utc(start).ceil('h').value,'left')

    def choose(self,known,side,reference):
        c=self.ctx;sell=side=='SELL'
        closed=int(np.searchsorted(c.o_end,known,'right'))-1
        if closed<0:return None
        price=c.target(sell,closed,known,reference,mode='leg',leg=None,swept=reference)
        if price is None:return None
        erl=[s[2] for s in c.tsw.at(closed) if s[1]==('L' if sell else 'H')]
        return {'price':float(price),'source':'origin_ERL_swing' if price in erl else 'fresh_opposing_key_level',
                'rule':'native target_mode=leg after consumed leg: next known ERL, else fresh origin/higher key level',
                'reference':float(reference),'selected_at':known.isoformat()}


def walk(frame,known,target,side,end,barrier=None,gap_check=None):
    """Wick target touch; same H1 bar as terminating close is ambiguous, not a win."""
    check=gap_check or (lambda start,end:bool(gaps(frame,start,end)))
    stop=min(end,barrier) if barrier is not None else end
    future=frame[(frame.index>=known)&(frame.index+pd.Timedelta(hours=1)<=stop)]
    touched=(future.high>=target) if side=='BUY' else (future.low<=target)
    first=future.index[touched][0] if touched.any() else None
    horizon=first+pd.Timedelta(hours=1) if first is not None else stop
    if check(known,horizon):return {'status':'censored_gap'}
    if first is not None:
        close=first+pd.Timedelta(hours=1)
        if barrier is not None and close==barrier:return {'status':'target_and_end_same_bar','observed_at':close.isoformat()}
        return {'status':'reached','observed_at':close.isoformat(),'hit_bar_open':first.isoformat()}
    return {'status':'ended_before_target' if barrier is not None and barrier<=end else 'unresolved_at_window_end'}


def measure_story(event,events,frame,window_end,selector,mode,max_stage=MAX_STAGE):
    if mode not in MODES or not 1<=max_stage<=5:raise ValueError('invalid target study profile')
    check=getattr(selector,'has_gap',lambda start,end:bool(gaps(frame,start,end)))
    row=event['row'];known=utc(event['observed_at']);side=row['side'];buy=side=='BUY';sign=1 if buy else -1
    key=event['story_key'];same=[e for e in events if e['story_key']==key and utc(e['observed_at'])>=known]
    endings=[utc(e['observed_at']) for e in same if e['kind'] in ('INVALIDATED','ENDED_FLIP','CANCELLED','LINE_END')]
    # Direct origin closes make the line-ending rule measurable even without a later transition event.
    ctx=selector.ctx
    closes=ctx.O['close']
    line_ends=[utc(t) for t,p in zip(ctx.o_end,closes) if known<t<=window_end and sign*(float(p)-row['level'])<0]
    line_end=min(line_ends) if line_ends else None
    primary_end=min(endings+[line_end]) if line_end is not None and endings else min(endings) if endings else line_end
    continuation=sorted({utc(e['observed_at']) for e in same if e['kind']=='CONTINUATION'})
    initial=float(row['target']);stages=[]
    prefix=frame[frame.index+pd.Timedelta(hours=1)<=known]
    breakout=row.get('breakout_time')
    before=prefix[prefix.index>=utc(breakout)] if breakout else prefix.tail(1)
    # erl_taken describes the FIRST proposed target, which the native engine may replace.
    # Check the ACTUAL frozen target, not that historical flag.
    extreme=float(before.high.max()) if buy else float(before.low.min())
    consumed=sign*(initial-extreme)<=0
    if consumed:
        stages.append({'stage':1,'target':initial,'selected_at':known.isoformat(),'status':'already_taken_at_confirmation'})
        return stages
    selected={'price':initial,'source':'native_frozen_bias_target','selected_at':known.isoformat()}
    for stage in range(1,max_stage+1):
        barrier=primary_end if stage==1 else line_end
        if barrier is not None and known>=barrier:
            stages.append({'stage':stage,'status':'line_ended_before_selection'});break
        if known>=window_end:
            stages.append({'stage':stage,'status':'unresolved_before_selection'});break
        # Refuse new decisions based on gap-adjacent context.
        if check(max(frame.index[0],known-pd.Timedelta(days=8)),known):
            stages.append({'stage':stage,'status':'censored_context_gap'});break
        result=walk(frame,known,selected['price'],side,window_end,barrier,check)
        stages.append(dict(selected,stage=stage,target=selected['price'],**result))
        if result['status']!='reached' or stage==max_stage:break
        hit=utc(result['observed_at'])
        if mode=='after_continuation_close':
            candidates=[t for t in continuation if t>=hit and t>known and (line_end is None or t<line_end) and t<window_end]
            if not candidates:
                stages.append({'stage':stage+1,'status':'no_new_continuation_close' if line_end is not None else 'unresolved_waiting_continuation'});break
            decision=candidates[0]
        else:decision=hit
        if check(hit,decision):
            stages.append({'stage':stage+1,'status':'censored_gap_before_selection'});break
        segment=frame[(frame.index>=utc(result['hit_bar_open']))&(frame.index+pd.Timedelta(hours=1)<=decision)]
        reference=max(selected['price'],float(segment.high.max())) if buy else min(selected['price'],float(segment.low.min()))
        chosen=selector.choose(decision,side,reference)
        if chosen is None:
            stages.append({'stage':stage+1,'status':'no_known_target_ahead','selected_at':decision.isoformat()});break
        selected=chosen;known=decision
    return stages


def run(results,inputs,out):
    results,inputs,out=map(Path,(results,inputs,out));out.mkdir(parents=True,exist_ok=True)
    records=[];first_summary={};selectors={}
    pairs=sorted(p.name for p in results.iterdir() if p.is_dir())
    for pair in pairs:
        native=sorted((results/pair).glob('window-*/native/ledger.sqlite'))
        if not native:continue
        report=json.loads(native[-1].with_name('report.json').read_text())
        cfg=report['manifest']['configuration'];start=utc(report['manifest']['start']);end=utc(report['manifest']['end'])
        frame,checksum,_=read_input(inputs/(pair+'_H1_ctrader.csv.gz'),start,end,max_rows=30000)
        if checksum!=report['manifest']['input_sha256']:raise ValueError('frozen input mismatch')
        selectors={tf:Selector(pair,frame,tf,cfg) for tf in ('D','W')}
        for path in native:
            r=json.loads(path.with_name('report.json').read_text());window_end=utc(r['manifest']['end'])
            with sqlite3.connect(path) as db:events=[json.loads(v) for v, in db.execute('SELECT payload FROM events')]
            for e in sorted(events,key=lambda x:(x['observed_at'],x['kind'])):
                if e['kind']!='CONFIRMED' or e.get('already_ended_at_observation'):continue
                for mode in MODES:
                    records.append({'pair':pair,'story_key':e['story_key'],'origin':e['row']['story'],
                        'side':e['row']['side'],'original_level':e['row']['level'],
                        'confirmed_at':e['observed_at'],'no_trade':bool(e['row'].get('no_trade')),
                        'window_end':window_end.isoformat(),'mode':mode,'stages':measure_story(e,events,frame,window_end,selectors[e['row']['story']],mode)})
        print(pair, 'measured',flush=True)
    counts=defaultdict(Counter)
    for r in records:
        for stage in r['stages']:
            for group in ('all_bias','eligible_only') if not r['no_trade'] else ('all_bias',):
                k=f"{r['origin']} / {r['mode']} / {group} / T{stage['stage']}"
                counts[k][stage['status']]+=1
    summary={'pairs':len(pairs),'confirmed_story_mode_records':len(records),'max_stage':MAX_STAGE,
        'selection_rule':'Frozen native primary target, then native ERL-first target beyond the consumed leg and all wicks already observed at decision; otherwise fresh origin/higher opposing KL. No live-rule change.',
        'modes':list(MODES),'code_sha256':digest(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))),
        'counts':{k:dict(v) for k,v in sorted(counts.items())},
        'limitations':['New target ladder is a specified research rule; historical alerts did not record successive targets.',
          'Window-end right censoring and missing-hour exclusions; shared stories/currencies are not independent.',
          'Target touch uses H1 bid wick, not body confirmation or tradable entry performance.',
          'Target touch and terminating origin close in same H1 candle is ambiguous, not a win.',
          'No target available and no new confirmation are not target failures; percentages must specify denominators.',
          'Only known native continuation-close events within each observation window are used.',
          'Primary already consumed by confirmation is separated; not counted as a new forward target hit.']}
    (out/'records.json').write_bytes(encoded(records));(out/'summary.json').write_bytes(encoded(summary))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',required=True);p.add_argument('--inputs',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();run(a.results,a.inputs,a.out)
