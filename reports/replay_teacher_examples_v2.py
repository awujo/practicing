"""Reproduce bounded teacher-plan diagnostics on existing frozen local alternate feeds.

No acquisition, fixture mutation, tolerance fitting or trading calls. The three
as-of minutes are independently read creation timestamps, NOT setup/fill times.
The exploratory scan windows are declared beforehand, not acceptance windows.
Run from repository root: python -m reports.replay_teacher_examples_v2
"""
import argparse
import gzip
from collections import Counter
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import signal
import time

from bishop.v2.engine import run
from bishop.v2.types import StrategyPolicy
from bishop.v2.simulation import Costs
from bishop.runner import replay_observations
from bishop.replay import evaluate

DATA='data/examples/EURGBP_pdf_p08_icmarkets_bid_H1.csv.gz'
MANIFEST=dict(symbol='EURGBP',tick_size='0.00001',distance_unit='0.0001',calendar_id='fx_ny_v1',anchor_id='ny17_wall_v2',price_basis='BID',source_id='icmarkets_kevin_frozen_815f153e',venue='ICMARKETS',base_tf='H1',sha256='815f153eccb7ac981c06850bab82a5cd39dd41146810497f7b115d0839d559b0')
CASES={
 'pdf-p08-eurgbp-buy-1':dict(as_of='2026-07-23T18:08:00Z',history_start='2026-06-28T21:00:00Z',scan_start='2026-07-22T00:00:00Z',review='knowledge-base/study/replay_p08_source_review.md'),
 'pdf-p37-eurgbp-sell-1':dict(as_of='2026-06-01T16:08:00Z',history_start='2026-05-03T21:00:00Z',scan_start='2026-05-29T00:00:00Z',review='knowledge-base/study/replay_eurgbp_other_source_review.md'),
 'pdf-p54-eurgbp-buy-1':dict(as_of='2026-05-14T19:09:00Z',history_start='2026-04-19T21:00:00Z',scan_start='2026-05-12T00:00:00Z',review='knowledge-base/study/replay_eurgbp_other_source_review.md'),
}
# New inputs are frozen copies of existing local Kevin exports, no downloads.
ADDITIONAL=json.loads(Path('reports/teacher_replay_v2/additional_local_inputs.json').read_text())
AVAILABLE_PAIRS={'EURGBP',*ADDITIONAL}
CASES.update({
 'pdf-p15-usdcad-sell-1':dict(as_of='2026-07-16T13:35:00Z',history_start='2026-06-21T21:00:00Z',scan_start='2026-07-14T00:00:00Z',review='knowledge-base/study/replay_other_pairs_source_review.md'),
 'pdf-p19-gbpjpy-buy-1':dict(as_of='2026-07-15T17:26:00Z',history_start='2026-06-21T21:00:00Z',scan_start='2026-07-13T00:00:00Z',review='knowledge-base/study/replay_other_pairs_source_review.md'),
 'pdf-p19-gbpjpy-buy-2':dict(as_of='2026-07-15T17:26:00Z',history_start='2026-06-21T21:00:00Z',scan_start='2026-07-13T00:00:00Z',review='knowledge-base/study/replay_other_pairs_source_review.md'),
 'pdf-p23-usdchf-sell-1':dict(as_of='2026-07-10T06:43:00Z',history_start='2026-06-14T21:00:00Z',scan_start='2026-07-08T00:00:00Z',review='knowledge-base/study/replay_chf_aud_source_review.md'),
 'pdf-p23-usdchf-sell-2':dict(as_of='2026-07-09T14:41:00Z',history_start='2026-06-14T21:00:00Z',scan_start='2026-07-08T00:00:00Z',review='knowledge-base/study/replay_chf_aud_source_review.md'),
 'pdf-p35-gbpjpy-buy-1':dict(as_of='2026-06-05T12:13:00Z',history_start='2026-05-10T21:00:00Z',scan_start='2026-06-03T00:00:00Z',review='knowledge-base/study/replay_other_pairs_source_review.md'),
 'pdf-p60-gbpaud-sell-1':dict(as_of='2026-05-12T08:52:00Z',history_start='2026-04-19T21:00:00Z',scan_start='2026-05-08T00:00:00Z',review='knowledge-base/study/replay_chf_aud_source_review.md'),
})


def input_for(pair):
    if pair=='EURGBP':return DATA,MANIFEST
    meta=ADDITIONAL[pair];manifest=dict(MANIFEST,symbol=pair,sha256=meta['sha256'],source_id='kevin_frozen_'+meta['sha256'][:16])
    if pair.endswith('JPY'):manifest.update(tick_size='0.001',distance_unit='0.01')
    return meta['path'],manifest


# These compare requested source protection versus the owner's distinct preset.
# There is no parameter search or selection of whichever profile looks closest.
PROFILES={'source_confirmation':('bishop_confirmation','context_liquidity'),
          'owner_fixed11':('owner_aggressive','owner_fixed11')}


class ReplayTimeBudgetExceeded(TimeoutError):
    pass


def budget_expired(*_):
    raise ReplayTimeBudgetExceeded('declared diagnostic time budget exceeded')


def digest(path): return sha256(Path(path).read_bytes()).hexdigest()


def diagnostic_groups(result,example):
    tick=Decimal(result['instrument']['tick_size'])
    stories={s['id']:s for s in result['stories']}
    orders={o['setup_id']:o for o in result['orders']}
    observations={o['id']:o for o in result['observations']}
    rejected={r['setup_id']:r for r in result['selection']['rejected']}
    aliases={r['setup_id']:r for r in result['selection'].get('aliases',[])}
    groups={}
    for s in result['setups']:
        if s['tf']!=example['tf'] or s['side']!=example['side']: continue
        key=(s['clock']['available_at'],s['model'],s['level_id'],s['entry_ticks'],s['stop_ticks'],s['target_ticks'],s['status'])
        if key not in groups:
            prices={k:str(Decimal(s[k+'_ticks'])*tick) if s[k+'_ticks'] is not None else None for k in ('entry','stop','target')}
            deltas={k:str(Decimal(prices[k])-Decimal(str(example[k]))) if prices[k] is not None and example.get(k) is not None else None for k in prices}
            groups[key]=dict(available_at=s['clock']['available_at'],model=s['model'],side=s['side'],tf=s['tf'],level_id=s['level_id'],status=s['status'],prices=prices,price_differences_from_printed_plan=deltas,
                representative_setup_id=s['id'],evidence_ids=s['evidence_ids'],risk_details=s['details'],contexts=[],selection=[],execution=[])
        group=groups[key];story=stories[s['story_id']]
        group['contexts'].append(dict(setup_id=s['id'],story_id=story['id'],origin_tf=story['origin_tf'],side=story['side'],route=story['route'],available_at=story['clock']['available_at']))
        if s['id'] in orders:
            order=orders[s['id']];group['selection'].append(dict(setup_id=s['id'],status='ORDERED',order_id=order['id']))
            group['execution'].append(observations[order['id']])
        elif s['id'] in aliases:group['selection'].append(dict(status='SAME_ECONOMIC_SIGNAL',**aliases[s['id']]))
        elif s['id'] in rejected:group['selection'].append(dict(status='REJECTED',**rejected[s['id']]))
        else:group['selection'].append(dict(setup_id=s['id'],status='UNRESOLVED_RISK_OR_TARGET'))
    return list(groups.values())



def plan_checkpoints(report):
    """Literal label diagnostics only; no fill/identity/acceptance inference."""
    source=report['source_plan'];groups=report['plan_groups']
    available=report['coverage']['timeframes'].get(source['tf'],{})
    if available.get('status')=='UNRESOLVED_RESOLUTION':
        return dict(status='ENTRY_RESOLUTION_UNAVAILABLE',exact_numeric_plan=False,source_route_identity='UNRESOLVED')
    trigger=source.get('trigger')
    families={'breakout':{'confirmation_bo'},'breakout_with_idm':{'confirmation_bo','confirmation_sweep_bos'},'engulfing':{'engulf_av_retest','confirmation_engulfed_oc','oc_break_retest'}}
    family=families.get(trigger)
    numerical=all(source.get(k) is not None for k in ('entry','stop','target'))
    def same(group,key):
        value=group['prices'].get(key)
        return value is not None and source.get(key) is not None and Decimal(value)==Decimal(str(source[key]))
    exact=[g['representative_setup_id'] for g in groups if numerical and all(same(g,k) for k in ('entry','stop','target'))]
    compatible=[g for g in groups if family and g['model'] in family]
    return dict(status='CONTEXT_ONLY_SOURCE_LABELS' if not numerical else 'EXACT_NUMERIC_PLAN_PRESENT_NOT_TRADE_ACCEPTANCE' if exact else 'NO_EXACT_NUMERIC_PLAN_ON_ALTERNATE_FEED',
        exact_numeric_plan=bool(exact),exact_plan_setup_ids=exact,
        same_side_tf_group_count=len(groups),entry_label_equal_groups=sum(same(g,'entry') for g in groups),
        compatible_named_family_groups=len(compatible) if family else None,
        compatible_family_entry_label_equal_groups=sum(same(g,'entry') for g in compatible) if family else None,
        source_route_identity='UNRESOLVED' if trigger in (None,'fourth_man') else 'NAMED_FAMILY_ONLY_CANDLE_IDENTITY_UNRESOLVED',
        rule='literal equality in a single causal plan; no tolerances fitted; cross-feed absence is not proof of a source-rule failure')

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--time-budget-seconds',type=int,default=180,help='Per-run POSIX time budget; 0 explicitly disables it')
    parser.add_argument('--index-only',action='store_true',help='Rebuild the index from compatible saved reports without engine runs')
    parser.add_argument('--case',choices=list(CASES),action='append')
    parser.add_argument('--profile',choices=list(PROFILES),action='append')
    parser.add_argument('--outdir',default='reports/teacher_replay_v2')
    parser.add_argument('--full-output',help='Optional local full-run directory; large diagnostics excluded by default')
    args=parser.parse_args(argv)
    if args.time_budget_seconds<0:parser.error('nonnegative time budget required')
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    fixtures=Path('tests/bishop_examples.json');fixture_hash=digest(fixtures)
    document=json.loads(fixtures.read_text());examples={e['id']:e for e in document['examples']}
    engine_paths=sorted(Path('bishop/v2').glob('*.py'))+[Path('bishop/runner.py'),Path('bishop/replay.py')]
    implementation_hash=sha256(''.join(str(p)+':'+digest(p)+'\n' for p in engine_paths).encode()).hexdigest()
    index=[];all_observations=[]
    for case_id in (() if args.index_only else args.case or CASES):
        case=CASES[case_id];example=examples[case_id]
        for profile in args.profile or ('source_confirmation',):
            source,risk=PROFILES[profile];entry_tfs=('M45',) if example['tf']=='M45' else ('H4','H2','H1')
            policy=StrategyPolicy(source_profile=source,risk_profile=risk,origin_tfs=('W','D','H4'),entry_tfs=entry_tfs)
            data,manifest=input_for(example['pair'])
            started=time.perf_counter()
            previous_handler=None
            if args.time_budget_seconds:
                previous_handler=signal.signal(signal.SIGALRM,budget_expired)
                signal.setitimer(signal.ITIMER_REAL,args.time_budget_seconds)
            try:
                result=run(data,manifest,as_of=case['as_of'],history_start=case['history_start'],scan_start=case['scan_start'],policy=policy,costs=Costs(),max_open_orders=10)
            except ReplayTimeBudgetExceeded:
                path=out/'run_limits.json'
                failures=json.loads(path.read_text()) if path.exists() else dict(scope='Aborted diagnostic runs, never zero-signal matches',runs=[])
                failure=dict(example_id=case_id,profile=profile,status='ABORTED_RUNTIME',implementation_sha256=implementation_hash,time_budget_seconds=args.time_budget_seconds)
                failures['runs'].append(failure);path.write_text(json.dumps(failures,indent=2)+'\n')
                print(json.dumps(failure),flush=True)
                continue
            finally:
                if previous_handler is not None:
                    signal.setitimer(signal.ITIMER_REAL,0)
                    signal.signal(signal.SIGALRM,previous_handler)
            observations=replay_observations(result);all_observations.extend(observations)
            groups=diagnostic_groups(result,example)
            report=dict(schema_version=1,scope='ALTERNATE_FEED_PLAN_DIAGNOSTIC_NOT_ACCEPTANCE',example_id=case_id,profile=profile,
                implementation=dict(commit_kind='base_revision_plus_working_tree_sha256',commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),sha256=implementation_hash),
                source_fixture_sha256=fixture_hash,source_review=case['review'],source_review_sha256=digest(case['review']),
                case_clock={**case,'clock_kind':'SOURCE_SNAPSHOT_ONLY','scan_window_kind':'EXPLORATORY_NOT_VERIFIED_SETUP_WINDOW'},
                source_plan={k:example.get(k) for k in ('pair','tf','side','entry','stop','target','source_feed','source_execution_status','trigger')},
                input=dict(path=data,**result['input']),policy=result['policy'],costs=result['costs'],coverage=result['coverage'],support=result['support'],
                selection={**{k:v for k,v in result['selection'].items() if k not in ('rejected','aliases')},'rejected_counts':dict(Counter(x['reason'] for x in result['selection']['rejected'])),'alias_count':len(result['selection'].get('aliases',[]))},summary=result['summary'],seconds=round(time.perf_counter()-started,3),
                strict_replay=evaluate({'schema_version':document['schema_version'],'examples':[example]},observations),
                context_counts=[dict(origin_tf=k[0],side=k[1],count=v) for k,v in Counter((s['origin_tf'],s['side']) for s in result['stories']).items()],
                plan_groups=groups,observations=observations,
                limitations=['Source FOREXCOM differs from frozen IC Markets BID feed.','H1 supports H1/H2/H4 only; requested M30/M5 pattern evidence is unavailable.','Exploratory scan and snapshot are not source setup/fill clocks.','Zero-cost hypothesis is for diagnostics, not profitability.','Printed plan differences do not establish association with a detector candidate.','No fixture tolerances or price labels were changed.'])
            report['plan_checkpoint_diagnostics']=plan_checkpoints(report)
            target=out/(case_id+'_'+profile+'.json.gz');target.write_bytes(gzip.compress((json.dumps(report,indent=2,allow_nan=False)+'\n').encode(),mtime=0))
            if args.full_output:
                full=Path(args.full_output);full.mkdir(parents=True,exist_ok=True);(full/(case_id+'_'+profile+'.json')).write_text(json.dumps(result,allow_nan=False)+'\n')
            index.append(dict(example_id=case_id,profile=profile,report=str(target),sha256=digest(target),seconds=report['seconds'],summary=result['summary'],plan_group_count=len(groups),strict_status=report['strict_replay']['status']))
            print(json.dumps(index[-1]),flush=True)
    if digest(fixtures)!=fixture_hash:raise RuntimeError('source fixture changed during replay')
    final_hash=sha256(''.join(str(p)+':'+digest(p)+'\n' for p in engine_paths).encode()).hexdigest()
    if final_hash!=implementation_hash:raise RuntimeError('implementation changed during replay')
    # Merge compatible saved case runs, never pool a different case or profile
    # into another case's acceptance check. Old implementation reports excluded.
    index=[];saved={}
    for case_id in CASES:
        for profile in PROFILES:
            target=out/(case_id+'_'+profile+'.json.gz')
            if not target.exists():continue
            report=json.loads(gzip.decompress(target.read_bytes()))
            if report['implementation']['sha256']!=implementation_hash or report['source_fixture_sha256']!=fixture_hash:continue
            if report['source_review_sha256']!=digest(report['source_review']):continue
            saved[(case_id,profile)]=report
            index.append(dict(example_id=case_id,profile=profile,report=str(target),sha256=digest(target),seconds=report['seconds'],summary=report['summary'],plan_group_count=len(report['plan_groups']),strict_status=report['strict_replay']['status']))
    by_profile={}
    for profile in PROFILES:
        rows=[]
        for example in document['examples']:
            report=saved.get((example['id'],profile))
            if report is None:
                rows.append(dict(id=example['id'],status='UNRESOLVED',reasons=['NOT_RUN: no local frozen pair input' if example['pair'] not in AVAILABLE_PAIRS else 'NOT_RUN in this implementation/profile']))
            else:
                rows.extend(evaluate({'schema_version':1,'examples':[example]},report['observations'])['results'])
        counts={status:sum(row['status']==status for row in rows) for status in ('PASS','FAIL','UNRESOLVED')}
        by_profile[profile]=dict(status='FAIL' if counts['FAIL'] else 'UNRESOLVED' if counts['UNRESOLVED'] else 'PASS',scope='SOURCE_POLICY_DIAGNOSTIC' if profile=='source_confirmation' else 'OWNER_EXPERIMENT_SEPARATE_FROM_SOURCE_ACCEPTANCE',counts=counts,results=rows)
    attempted={i['example_id'] for i in index}
    final=dict(schema_version=2,scope='Teacher replay first pass; unresolved inputs are counted',fixture_sha256=fixture_hash,implementation_sha256=implementation_hash,runs=index,
        attempted_cases=sorted(attempted),unattempted=[dict(example_id=e['id'],reason='NO_LOCAL_FROZEN_PAIR_INPUT' if e['pair'] not in AVAILABLE_PAIRS else 'NOT_REQUESTED_IN_THIS_RUN') for e in document['examples'] if e['id'] not in attempted],
        strict_replay_by_profile=by_profile,run_limits=json.loads((out/'run_limits.json').read_text()) if (out/'run_limits.json').exists() else {'runs':[]})
    (out/'index.json').write_text(json.dumps(final,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
