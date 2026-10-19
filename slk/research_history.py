"""Windowed native-engine research over frozen history, plus scenario sidecars. No broker access."""
import argparse
import json
from pathlib import Path
import sqlite3
import time

import pandas as pd
from .research import encoded, read_input, digest
from .research_replay import run_pair, utc
from .research_scenarios import study


def windows(first, end, size=90):
    if not 1<=size<=90:raise ValueError('window size 1..90')
    begin=first+pd.Timedelta(days=365)
    while begin<end:
        finish=min(begin+pd.Timedelta(days=size),end)
        yield begin,finish
        begin=finish


def run(root,pair,out,seconds=9600):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if not 60<=seconds<=9600:raise ValueError('history budget 60..9600 seconds')
    m=json.loads((root/'batch.json').read_text())
    if m['source']!='ctrader' or pair not in m['selected_pairs']:raise ValueError('wrong frozen source/pair')
    entry=next(e for e in m['entries'] if e['pair']==pair)
    if entry['status']!='ready' or entry['file']!=pair+'_H1_ctrader.csv.gz':raise ValueError('input not ready')
    path=root/entry['file'];start=utc(m['start']);end=utc(m['end'])
    frame,checksum,_=read_input(path,start,end,max_rows=30000)
    first=frame.index[0];schedule=list(windows(first,end))
    if not 1<=len(schedule)<=10:raise ValueError('history requires 1..10 windows')
    begun=time.monotonic();rows=[];deadline=begun+seconds
    for number,(begin,finish) in enumerate(schedule):
        folder=out/f'window-{number:02d}';identity={'input_sha':checksum,'pair':pair,'begin':begin.isoformat(),
            'end':finish.isoformat(),'code_sha':digest(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py'))))}
        done=folder/'completed.json'
        if done.exists() and json.loads(done.read_text()).get('identity')==identity:
            rows.append(json.loads(done.read_text()));continue
        record={'identity':identity,'status':'budget_exhausted'}
        remaining=deadline-time.monotonic()
        if remaining<30:rows.append(record);break
        try:
            result=run_pair(path,pair,start,finish,begin,folder/'native',min(600,int(remaining)-20),
                            origins=('D','W'),entry_cap=128,skip_recent_gaps=True,ledger_pages=2048)
            record.update(status=result['status'],events=result['event_count'],steps=result['decision_steps'],
                          skipped_cutoffs=result['skipped_h4_cutoffs'],entry_status=result['entry_study']['status'])
            if result['status']=='complete':
                with sqlite3.connect(folder/'native/ledger.sqlite') as conn:
                    expanded=study(conn,frame,end,folder/'scenarios',min(240,max(1,int(deadline-time.monotonic()))))
                record['scenario_status']=expanded['status'];record['scenario_records']=expanded['records']
                if expanded['status']!='complete' or result['entry_study']['status']!='complete':record['status']='partial'
            if record['status']=='complete':done.write_bytes(encoded(record))
        except Exception as exc:
            record.update(status='failed',error_type=type(exc).__name__)
        rows.append(record)
        summary={'pair':pair,'planned_windows':len(schedule),'windows':rows,'evaluation_days':(end-first).total_seconds()/86400-365,
                 'status':'complete' if len(rows)==len(schedule) and all(r['status']=='complete' for r in rows) else 'partial',
                 'note':'Full available history after 365-day warmup; native Daily/Weekly stories; H1 execution. Gap-adjacent cutoffs skipped and bootstrap reset; counts explicit. Windows reset state and censor some boundary entries; context configuration is code defaults, not live DB settings. All inspected periods exploratory, no untouched holdout.'}
        (out/'history-report.json').write_bytes(encoded(summary))
    # Always save even when budget was exhausted before starting the next window.
    summary={'pair':pair,'planned_windows':len(schedule),'windows':rows,
             'evaluation_days':(end-first).total_seconds()/86400-365,
             'status':'complete' if len(rows)==len(schedule) and all(r['status']=='complete' for r in rows) else 'partial',
             'limitations':['H1 intrabar ambiguity; M5 not available','code defaults rather than live DB configuration',
                'eight-day gap exclusion and rebootstrap; older history gaps may affect context',
                '90-day windows rebootstrap, censor boundary entry searches; no portfolio model',
                'all historical results exploratory, not untouched confirmatory evidence']}
    (out/'history-report.json').write_bytes(encoded(summary))
    print(json.dumps(summary,indent=2));return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--pair',required=True)
    p.add_argument('--out',required=True);p.add_argument('--seconds',type=int,default=9600)
    a=p.parse_args();r=run(a.input,a.pair,a.out,a.seconds);raise SystemExit(0 if r['status']=='complete' else 2)
