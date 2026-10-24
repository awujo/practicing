"""Plan or explicitly collect frozen IC Markets teacher diagnostic inputs.

Planning is offline. Collection permits authentication, symbols and historical
bars only; borrowed credentials are never refreshed or written. No fallback feed.
"""
import argparse
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import os

from bishop.v2.types import utc, stable_id
from bishop.v2.aggregation import is_open
from ctrader.client import CTraderClient
from ctrader import tokens
from ctrader.framing import oa, model


class ReadOnlySettings:
    borrowed = True
    def __init__(self, settings): self.settings=settings
    def get(self, key, default=None): return self.settings.get(key,default)
    def set(self, *args, **kwargs): raise RuntimeError('borrowed settings are read-only')


def borrowed_settings():
    # Direct SELECT-only shared table adapter; no Bishop settings/kill-switch probe.
    if os.environ.get('DATABASE_URL'):
        from bishop import db
        return ReadOnlySettings(tokens.DbSettings(db,token_table='settings'))
    return ReadOnlySettings(tokens.MemorySettings(borrowed=True))


class HistoricalClient(CTraderClient):
    """Fail closed before any non-allowlisted API request or token refresh."""
    def __init__(self, *args, settings=None, **kwargs):
        super().__init__(*args,settings=ReadOnlySettings(settings if settings is not None else borrowed_settings()),**kwargs)
    def _refresh(self): raise RuntimeError('collection never refreshes borrowed tokens')
    def account_auth(self):
        access=tokens.load_tokens(self.settings)['access_token']
        if not access: raise RuntimeError('borrowed access token unavailable')
        self._account_auth(access)  # invalid/expired token propagates; Kevin owns refresh
    def request(self, msg, *args, **kwargs):
        allowed=(oa.ProtoOAApplicationAuthReq,oa.ProtoOAGetAccountListByAccessTokenReq,
                 oa.ProtoOAAccountAuthReq,oa.ProtoOASymbolsListReq,
                 oa.ProtoOASymbolByIdReq,oa.ProtoOAGetTrendbarsReq)
        if not isinstance(msg,allowed): raise RuntimeError('non-historical request refused')
        return super().request(msg,*args,**kwargs)


def build_plan(fixtures, warmup_days=35, context_days=400, forward_days=14, clock_annotations=None, annotations_only=False):
    if type(warmup_days) is not int or warmup_days<35 or type(context_days) is not int or context_days<warmup_days:
        raise ValueError('require >=35 base warmup days and context >= base warmup')
    if type(forward_days) is not int or forward_days<0: raise ValueError('nonnegative forward_days required')
    annotations={a['example_id']:a for a in (clock_annotations or {}).get('annotations',[])}
    if len(annotations)!=len((clock_annotations or {}).get('annotations',[])):raise ValueError('duplicate clock annotations')
    known={c['id']:c for c in fixtures['examples']}
    if set(annotations)-set(known):raise ValueError('unknown annotated example')
    for cid,a in annotations.items():
        if a['pair']!=known[cid]['pair']:raise ValueError('annotation pair mismatch')
    if annotations_only and not annotations:raise ValueError('annotations_only requires clock annotations')
    inventory=[]; pending={}
    for case in fixtures['examples']:
        stamp=case.get('chart_snapshot_date')
        item={'id':case['id'],'pair':case['pair'],'tf':case['tf'],
              'source_feed':case.get('source_feed'),'chart_snapshot_date':stamp,
              'setup_time':case.get('setup_time'),'fill_time':case.get('time'),
              'clock_readiness':'UNRESOLVED_SETUP_FILL_CLOCKS' if not case.get('setup_time') or not case.get('time') else 'DECLARED_CLOCKS',
              'status':'PLANNED_SNAPSHOT_WINDOW' if stamp else 'UNRESOLVED_DATE'}
        annotation=annotations.get(case['id'])
        if annotation:
            if stamp:raise ValueError('annotations must not replace fixture snapshot dates')
            search_start,search_end=map(utc,annotation['candidate_event_search'])
            collect_start,collect_end=map(utc,annotation['candidate_collection'])
            if not collect_start<=search_start<search_end<=collect_end:raise ValueError('invalid exploratory annotation bounds')
            item.update(status='EXPLORATORY_ANNOTATED_WINDOW',clock_annotation=annotation)
            for tf,days in [('M5',warmup_days),('H1',context_days)]:
                pending.setdefault((case['pair'],tf),[]).append((min(collect_start,search_start-timedelta(days=days)),collect_end,case['id']))
        inventory.append(item)
        if not stamp or annotations_only: continue
        day=utc(stamp+'T00:00:00Z')
        for tf,days in [('M5',warmup_days),('H1',context_days)]:
            pending.setdefault((case['pair'],tf),[]).append((day-timedelta(days=days),day+timedelta(days=1+forward_days),case['id']))
    jobs=[]
    for (pair,tf),ranges in sorted(pending.items()):
        merged=[]
        for a,b,cid in sorted(ranges):
            if merged and a<=merged[-1][1]:
                merged[-1][1]=max(b,merged[-1][1]);merged[-1][2].append(cid)
            else: merged.append([a,b,[cid]])
        for a,b,ids in merged:
            jobs.append({'id':stable_id('collect',pair,tf,a,b),'pair':pair,'base_tf':tf,'start':a.isoformat(),'end':b.isoformat(),'case_ids':sorted(ids),'exploratory_case_ids':sorted(cid for cid in ids if cid in annotations),'clock_annotations':{cid:annotations[cid] for cid in ids if cid in annotations}})
    return {'schema_version':'teacher_collection_v1','plan_scope':'ANNOTATED_EXPLORATORY_ONLY' if annotations_only else 'FIXTURES_PLUS_ANNOTATIONS' if annotations else 'FIXTURE_SNAPSHOT_WINDOWS','provider':'IC Markets cTrader Open API','purpose':'alternate-feed diagnostic, not source-feed equivalence','base_warmup_days':warmup_days,'context_warmup_days':context_days,'forward_days':forward_days,'inventory':inventory,'jobs':jobs}


def exact_prices(tb):
    """Protocol prices are integer 1e-5 units; never pass through float."""
    lo=int(tb.low)
    prices=tuple(Decimal(v)/Decimal(100000) for v in (lo+int(tb.deltaOpen),lo+int(tb.deltaHigh),lo,lo+int(tb.deltaClose)))
    o,h,l,c=prices
    if not l<=min(o,c)<=max(o,c)<=h: raise ValueError('invalid protocol OHLC geometry')
    return prices


def collect_job(client, job, metadata, out_dir, retrieved_at=None):
    # Alias and calendar conventions are independently declared, never guessed.
    required=('broker_symbol','calendar_id','anchor_id','calendar_version','asset_class')
    if any(k not in metadata for k in required): raise ValueError('explicit symbol/calendar metadata required: '+', '.join(required))
    if metadata['calendar_id']=='explicit_intervals_v1' and 'calendar' not in metadata: raise ValueError('explicit interval calendar missing')
    info=client.symbol(metadata['broker_symbol'])
    if info['name']!=metadata['broker_symbol']: raise ValueError('broker symbol resolved to a different name')
    start,end=utc(job['start']),utc(job['end']); period=job['base_tf']
    if period not in ('M5','H1') or end<=start: raise ValueError('invalid planned duration/period')
    got={}; volumes={}; cursor=start; request_count=0; chunks=[]
    while cursor<end:
        stop=min(cursor+timedelta(days=7 if period=='H1' else 1),end)
        response=client._hist_request(oa.ProtoOAGetTrendbarsReq(ctidTraderAccountId=client.account_id,symbolId=info['symbol_id'],period=model.ProtoOATrendbarPeriod.Value(period),fromTimestamp=int(cursor.timestamp())*1000,toTimestamp=int(stop.timestamp())*1000))
        request_count+=1
        chunk_times=[]
        for tb in response.trendbar:
            at=datetime.fromtimestamp(int(tb.utcTimestampInMinutes)*60,timezone.utc)
            if not cursor<=at<stop: continue
            if int(at.timestamp()) % (300 if period=='M5' else 3600): raise ValueError('unaligned historical candle')
            prices=exact_prices(tb)
            # Display digit precision is not evidence for rounding raw protocol data.
            tick=Decimal(10)**-int(info['digits'])
            if any(p/tick!=(p/tick).to_integral_value() for p in prices): raise ValueError('protocol prices off broker display grid')
            if at in got and (got[at]!=prices or volumes[at]!=int(getattr(tb,'volume',0))): raise ValueError('conflicting historical bars')
            got[at]=prices; volumes[at]=int(getattr(tb,'volume',0));chunk_times.append(at)
        chunks.append({'requested_start':cursor.isoformat(),'requested_end':stop.isoformat(),'returned_rows':len(response.trendbar),'retained_rows':len(chunk_times),'first_bar':min(chunk_times).isoformat() if chunk_times else None,'last_bar':max(chunk_times).isoformat() if chunk_times else None,'empty':not chunk_times,'completeness':'UNVALIDATED_NO_PAGINATION_FLAG'})
        cursor=stop
    if not got: raise RuntimeError('no historical bars returned; no substitute feed')
    text=io.StringIO(newline=''); writer=csv.writer(text,lineterminator='\n');writer.writerow(('time','open','high','low','close','volume'))
    for at,prices in sorted(got.items()):writer.writerow((at.isoformat(),*(format(p,'f') for p in prices),volumes[at]))
    raw=gzip.compress(text.getvalue().encode(),mtime=0)
    directory=Path(out_dir);directory.mkdir(parents=True,exist_ok=True)
    path=directory/(job['id']+'.csv.gz'); manifest_path=path.with_suffix('.manifest.json')
    if path.exists() or manifest_path.exists(): raise FileExistsError('frozen snapshot already exists')
    manifest={**metadata,'symbol':job['pair'],'tick_size':format(Decimal(10)**-int(info['digits']),'f'),'distance_unit':format(Decimal(10)**-int(info['pip_position']),'f'),'price_basis':'BID','venue':'ICMARKETS','provider':'IC Markets cTrader Open API','base_tf':period,'source_id':stable_id('source','ICMARKETS',client.env,info['symbol_id'],metadata['broker_symbol'],period),'sha256':sha256(raw).hexdigest(),'retrieved_at':utc(retrieved_at or datetime.now(timezone.utc)).isoformat(),'historical_availability_assumption':'bar close; actual historical receipt timestamps unavailable','requested_start':start.isoformat(),'requested_end':end.isoformat(),'first_bar':min(got).isoformat(),'last_bar':max(got).isoformat(),'rows':len(got),'symbol_metadata':info,'request_count':request_count,'chunks':chunks,'empty_chunks':sum(c['empty'] for c in chunks),'zero_volume_rows':sum(v==0 for v in volumes.values()),'observed_outside_fx_weekend_hours':sum(not is_open(at,'fx_ny_v1') for at in got),'calendar_observation_note':'FX weekend diagnostic only; not an assumed calendar for non-FX; observed bars retained','raw_collection_status':'RAW_COLLECTED_UNVALIDATED','case_ids':job['case_ids'],'collection_job':dict(job),'coverage_status':'NOT_CALENDAR_VALIDATED','source_equivalence':'ALTERNATE_FEED; teacher feed/alignment may differ'}
    path.write_bytes(raw);manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    return {'path':str(path),'manifest':str(manifest_path),'sha256':manifest['sha256'],'rows':len(got)}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixtures',default='tests/bishop_examples.json');p.add_argument('--plan-out',default='reports/teacher_collection_plan.json');p.add_argument('--warmup-days',type=int,default=35);p.add_argument('--context-days',type=int,default=400);p.add_argument('--forward-days',type=int,default=14)
    p.add_argument('--clock-annotations');p.add_argument('--annotations-only',action='store_true');p.add_argument('--plan-only',action='store_true');p.add_argument('--pairs',nargs='+');p.add_argument('--collect',action='store_true');p.add_argument('--metadata',help='explicit pair -> broker symbol/calendar metadata JSON');p.add_argument('--out-dir','--out',dest='out_dir',default='data/teacher_icmarkets');p.add_argument('--job-id',action='append')
    a=p.parse_args(argv);fixture_path=Path(a.fixtures);plan=build_plan(json.loads(fixture_path.read_text()),a.warmup_days,a.context_days,a.forward_days,json.loads(Path(a.clock_annotations).read_text()) if a.clock_annotations else None,a.annotations_only);plan['fixtures_sha256']=sha256(fixture_path.read_bytes()).hexdigest()
    if a.clock_annotations:plan['clock_annotations_sha256']=sha256(Path(a.clock_annotations).read_bytes()).hexdigest()
    plan_path=Path(a.plan_out);plan_path.parent.mkdir(parents=True,exist_ok=True);plan_path.write_text(json.dumps(plan,indent=2)+'\n')
    if not a.collect or a.plan_only: return 0
    if not a.metadata: p.error('--collect requires explicit --metadata')
    metadata=json.loads(Path(a.metadata).read_text())
    requested=None
    if a.pairs is not None:
        requested={piece.strip().upper() for token in a.pairs for piece in token.split(',') if piece.strip()}
        if not requested: p.error('empty --pairs selection')
        known={i['pair'] for i in plan['inventory']}
        if 'ALL' in requested:
            if requested!={'ALL'}: p.error('ALL cannot be mixed with individual pairs')
            requested=None
        elif requested-known: p.error('unknown --pairs selection')
    jobs=[j for j in plan['jobs'] if (not a.job_id or j['id'] in a.job_id) and (requested is None or j['pair'] in requested)]
    if not jobs: p.error('selection has no dated collection jobs')
    if a.job_id and set(a.job_id)-{j['id'] for j in jobs}:p.error('unknown job id')
    if any(j['pair'] not in metadata for j in jobs):p.error('metadata missing for requested pairs')
    directory=Path(a.out_dir);directory.mkdir(parents=True,exist_ok=True)
    (directory/'collection_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    status={'schema_version':'teacher_acquisition_status_v1','status':'STARTING','plan_sha256':sha256(plan_path.read_bytes()).hexdigest(),'requested_jobs':len(jobs),'expected_jobs':len(jobs),'jobs':[]}
    def save_status():
        (directory/'acquisition_status.json').write_text(json.dumps(status,indent=2)+'\n')
    save_status();client=None
    try:
        client=HistoricalClient();client.connect();client.app_auth();client.account_auth()
    except Exception as exc:
        status.update(status='AUTH_OR_CONNECTION_FAILED',error_type=type(exc).__name__)
        save_status()
        if client is not None: client.close()
        return 1
    try:
        for job in jobs:
            try:
                result=collect_job(client,job,metadata[job['pair']],a.out_dir)
                status['jobs'].append({'id':job['id'],'pair':job['pair'],'base_tf':job['base_tf'],'status':'RAW_COLLECTED_UNVALIDATED',**result})
            except Exception as exc:
                # Never persist exception text: remote diagnostics may contain IDs.
                status['jobs'].append({'id':job['id'],'pair':job['pair'],'base_tf':job['base_tf'],'status':'FAILED','error_type':type(exc).__name__})
            status['status']='COLLECTING';save_status()
    finally:
        client.close()
    successes=sum(j['status']=='RAW_COLLECTED_UNVALIDATED' for j in status['jobs'])
    status.update(status='RAW_COLLECTED_UNVALIDATED' if successes==len(jobs) else 'PARTIAL' if successes else 'FAILED',collected_jobs=successes,failed_jobs=len(jobs)-successes)
    save_status()
    print(json.dumps({'status':status['status'],'collected_jobs':successes,'failed_jobs':len(jobs)-successes}))
    return 0 if successes==len(jobs) else 1

if __name__=='__main__':raise SystemExit(main())
