import json,sqlite3,collections,statistics,csv
from pathlib import Path
import argparse
p=argparse.ArgumentParser();p.add_argument('--input',default='.');args=p.parse_args()
root=Path(args.input);src=root/'raw';summary=json.loads((root/'history-summary.json').read_text());a=summary['analysis']
events={};scenarios={};reports=[];trials=[];duplicate=0
for p in sorted(src.glob('*/window-*/native/ledger.sqlite')):
 pair=p.parts[-4];c=sqlite3.connect(p)
 for eid,payload in c.execute('select id,payload from events'):
  key=(pair,eid);duplicate+=key in events;events[key]=json.loads(payload)
 for eid,variant,payload in c.execute('select event_id,variant,payload from entry_trials'):
  trials.append(dict(pair=pair,eid=eid,variant=variant,**json.loads(payload)))
 reports.append(json.loads(p.with_name('report.json').read_text()))
for p in sorted(src.glob('*/window-*/scenarios/ledger.sqlite')):
 pair=p.parts[-4];c=sqlite3.connect(p)
 for rid,payload in c.execute('select id,payload from scenarios'):
  v=json.loads(payload);key=(pair,v['family'],v['event_id'],v.get('entry_variant'),v.get('alternative'));scenarios[key]=dict(v,pair=pair)
ss=list(scenarios.values());es=[v for v in ss if v['family']=='entry_counterfactual'];ls=[v for v in ss if v['family']=='lifecycle']
def stat(vals):
 vals=list(vals)
 return dict(n=len(vals),mean=statistics.mean(vals) if vals else None,median=statistics.median(vals) if vals else None,positive=sum(x>0 for x in vals),minimum=min(vals) if vals else None,maximum=max(vals) if vals else None)
def matched(variant,alt):
 base={(v['pair'],v['event_id']):v for v in es if v['entry_variant']==variant and v['alternative']=='baseline'}
 alternative={(v['pair'],v['event_id']):v for v in es if v['entry_variant']==variant and v['alternative']==alt}
 keys=[k for k in base.keys()&alternative.keys() if base[k]['result']['status']=='closed' and alternative[k]['result']['status']=='closed']
 return dict(n=len(keys),baseline=stat(base[k]['result']['result_R'] for k in keys),alternative=stat(alternative[k]['result']['result_R'] for k in keys),
             delta=stat(alternative[k]['result']['result_R']-base[k]['result']['result_R'] for k in keys))
baseline={};reentry={};byorigin={}
for variant in ('H1_zone','H1_rejection','H2_zone','H4_zone'):
 vs=[v for v in es if v['entry_variant']==variant and v['alternative']=='baseline'];closed=[v for v in vs if v['result']['status']=='closed'];stops=[v for v in vs if v['result'].get('exit')=='stop']
 baseline[variant]=dict(closed=stat(v['result']['result_R'] for v in closed),exits=dict(collections.Counter(v['result'].get('exit') for v in closed)),ambiguous_closed=sum(v['result'].get('ambiguous_bar',False) for v in closed),ambiguous_stops=sum(v['result'].get('ambiguous_bar',False) for v in stops),stops=len(stops),unambiguous=stat(v['result']['result_R'] for v in closed if not v['result'].get('ambiguous_bar')),byyear={year:stat(v['result']['result_R'] for v in closed if v['observed_at'][:4]==year) for year in ('2024','2025','2026')})
 for origin in ('D','W'):
  byorigin[variant+'/'+origin]=stat(v['result']['result_R'] for v in closed if events[(v['pair'],v['event_id'])]['row']['story']==origin)
 for kind in ('same_direction_reentry','opposite_direction_setup'):
  eligible=[v for v in vs if v['result'].get('exit')=='stop'];rr=[(v,v[kind]) for v in eligible if v.get(kind,{}).get('status')=='closed']
  reentry[variant+'/'+kind]=dict(eligible_stops=len(eligible),closed=stat(r['result_R'] for v,r in rr),ambiguous=sum(r.get('ambiguous_bar',False) for v,r in rr),baseline_matched=stat(v['result']['result_R'] for v,r in rr),combined_equal_cash_risk=stat(v['result']['result_R']+r['result_R'] for v,r in rr))
# Canonical accepted baseline signal per pair/origin/time/side, newest tap first.
canonical={}
for v in ls:
 if not v.get('policies',{}).get('keep'):continue
 e=events[(v['pair'],v['event_id'])];f=v['features'];k=(v['pair'],f['story_tf'],v['observed_at'],f['side']);priority=(f.get('story_age_hours') or 0,v['event_id'])
 if k not in canonical or priority<canonical[k][0]:canonical[k]=(priority,v)
canon=[v[1] for v in canonical.values()]
def lifecycle_stats(vals,h='24'):
 vs=[v for v in vals if v['outcomes'][h]['status']=='observed'];numbers=[v['outcomes'][h]['endpoint_range'] for v in vs]
 return dict(stat(numbers),unique_times=len(set(v['observed_at'] for v in vs)),stories=len(set(v['story_key'] for v in vs)))
cohorts={}
for tf in ('D','W'):
 vs=[v for v in canon if v['features']['story_tf']==tf]
 for year in ('all','2024','2025','2026'):
  chosen=vs if year=='all' else [v for v in vs if v['observed_at'][:4]==year]
  cohorts[tf+'/'+year]=lifecycle_stats(chosen)
 for name,fn in [('initial',lambda e:e['kind']=='CONFIRMED'),('pretarget_cont',lambda e:e['kind']=='CONTINUATION' and e['row']['status']=='CONFIRMED'),('posttarget_cont',lambda e:e['kind']=='CONTINUATION' and e['row']['status']=='TARGET_HIT')]:
  cohorts[tf+'/'+name]=lifecycle_stats([v for v in vs if fn(events[(v['pair'],v['event_id'])])])
pairs=[]
for pair in sorted(set(v['pair'] for v in canon)):
 row={'pair':pair}
 for tf in ('D','W'):
  st=lifecycle_stats([v for v in canon if v['pair']==pair and v['features']['story_tf']==tf]);row[tf+'_n']=st['n'];row[tf+'_mean']=st['mean']
 for var in ('H1_zone','H1_rejection','H2_zone','H4_zone'):
  chosen=[v for v in es if v['pair']==pair and v['entry_variant']==var and v['alternative']=='baseline' and v['result']['status']=='closed'];st=stat(v['result']['result_R'] for v in chosen);row[var+'_closed']=st['n'];row[var+'_mean_R']=st['mean']
 pairs.append(row)
result=dict(pairs=28,windows=len(reports),native_events=len(events),duplicate_native_events=duplicate,kind_counts=dict(collections.Counter(e['kind'] for e in events.values())),steps=sum(r['decision_steps'] for r in reports),skips=sum(r['skipped_h4_cutoffs'] for r in reports),confirmations=sum(r['entry_study']['eligible_confirmations'] for r in reports),entry_trials=len(trials),trial_statuses=dict(collections.Counter(t['status'] for t in trials)),baseline=baseline,reentry=reentry,byorigin=byorigin,cohorts=cohorts,matched={v+'/'+alt:matched(v,alt) for v in ('H1_zone','H1_rejection','H2_zone','H4_zone') for alt in ('stop_1p5_risk','stop_H1_structure','stop_H2_structure','stop_H4_structure','target_3R','partial_then_breakeven','trail_closed_H1')},pairs_table=pairs)
(root/'audit-summary.json').write_text(json.dumps(result,indent=2));(root/'counterfactuals.json').write_text(json.dumps(es));(root/'lifecycle.json').write_text(json.dumps(ls))
with open(root/'pairs.csv','w') as f:w=csv.DictWriter(f,pairs[0]);w.writeheader();w.writerows(pairs)
print(json.dumps({k:v for k,v in result.items() if k not in ('matched','pairs_table','reentry')},indent=2));print('REENTRY',json.dumps(reentry));print('MATCHED',json.dumps({k:v for k,v in result['matched'].items() if k.startswith('H1_zone') or k.startswith('H1_rejection/stop_H4')}))
