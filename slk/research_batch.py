"""Offline bounded replay batch. Consumption of explicitly exported data only."""
import argparse
import json
from pathlib import Path
import time
from .research import atomic_json, utc
from .research_collect import select
from .research_replay import run_pair


def run(root, out, seconds=600):
    if not 1<=seconds<=600:raise ValueError('batch budget 1..600 seconds')
    root=Path(root).resolve(); out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if (root/'batch.json').stat().st_size>100000:raise ValueError('batch manifest oversized')
    m=json.loads((root/'batch.json').read_text());entries=m['entries']
    if not 1<=len(entries)<=4:raise ValueError('batch must contain 1..4 pairs')
    names, chosen = select(','.join(m['requested_pairs']), m['offset'], len(entries))
    if m['source'] != 'ctrader' or chosen != m['selected_pairs'] or [e['pair'] for e in entries] != chosen:
        raise ValueError('inconsistent batch provenance')
    if m['next_offset'] != (m['offset']+len(chosen) if m['offset']+len(chosen)<len(names) else None):
        raise ValueError('inconsistent continuation offset')
    start,end,evaluation=utc(m['start']),utc(m['end']),utc(m['evaluation_start'])
    if not start+__import__('pandas').Timedelta(days=365)<=evaluation<end or end-start>__import__('pandas').Timedelta(days=1500) or end-evaluation>__import__('pandas').Timedelta(days=90):
        raise ValueError('invalid batch dates/warmup')
    for e in entries:
        if e['status'] not in ('ready','acquisition_failed','budget_exhausted'):
            raise ValueError('invalid acquisition status')
        if e['status']=='ready' and e.get('file')!=e['pair']+'_H1_ctrader.csv.gz':
            raise ValueError('invalid export symbol')
    begun=time.monotonic();results=[]
    for entry in entries:
        if entry['status']!='ready':results.append(entry);continue
        remaining=seconds-(time.monotonic()-begun)
        if remaining<2:results.append({'pair':entry['pair'],'status':'budget_exhausted'});continue
        pair=entry['pair'];path=(root/entry['file']).resolve()
        if path.parent!=root or path.name!=pair+'_H1_ctrader.csv.gz':raise ValueError('invalid manifest path/symbol')
        try:
            result=run_pair(path,pair,m['start'],m['end'],m['evaluation_start'],out/pair,min(140,int(remaining)))
            results.append({'pair':pair,'status':result['status'],'events':result['event_count'],'steps':result['decision_steps']})
        except Exception as exc:
            results.append({'pair':pair,'status':'failed','error_type':type(exc).__name__})
        atomic_json(out/'batch-report.json',{'requested_pairs':m['requested_pairs'],'selected_pairs':m['selected_pairs'],
            'next_offset':m['next_offset'],'retry_pairs':[r['pair'] for r in results if r['status']!='complete'],'results':results,'note':'Manual bounded research; no live strategy changes.'},out,max_bytes=40*1024**2)
    atomic_json(out/'batch-report.json',{'requested_pairs':m['requested_pairs'],'selected_pairs':m['selected_pairs'],
        'next_offset':m['next_offset'],'retry_pairs':[r['pair'] for r in results if r['status']!='complete'],'results':results,'wall_seconds':round(time.monotonic()-begun,2),
        'note':'Exploratory event study. No portfolio or profitability conclusions.'},out,max_bytes=40*1024**2)
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--out',default='research-results')
    a=p.parse_args();results=run(a.input,a.out);print(json.dumps(results,indent=2));raise SystemExit(0 if all(r['status']=='complete' for r in results) else 2)
