"""Read current cTrader symbol schedule evidence without certifying history.

No weekday origin, timezone/DST or historical holiday semantics are inferred.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from bishop.collect_teacher_data import HistoricalClient
from bishop.v2.types import utc
from ctrader.framing import oa


def _present(message, name):
    try:return message.HasField(name)
    except (AttributeError,ValueError):return hasattr(message,name)


def schedule_record(symbol, name):
    out={'symbolId':int(symbol.symbolId),'name':name,'digits':int(symbol.digits),'pipPosition':int(symbol.pipPosition)}
    if _present(symbol,'scheduleTimeZone'):out['scheduleTimeZone']=symbol.scheduleTimeZone
    out['schedule']=[{'startSecond':int(i.startSecond),'endSecond':int(i.endSecond)} for i in symbol.schedule]
    fields=('holidayId','name','description','scheduleTimeZone','holidayDate','isRecurring','startSecond','endSecond')
    out['holiday']=[{field:getattr(h,field) for field in fields if _present(h,field)} for h in symbol.holiday]
    return out


def collect_symbol_schedules(client, metadata, out, retrieved_at=None):
    records=[];failures=[]
    for pair,meta in sorted(metadata.items()):
        try:
            name=meta['broker_symbol'];info=client.symbol(name)
            if info['name']!=name:raise ValueError('different resolved symbol')
            response=client.request(oa.ProtoOASymbolByIdReq(ctidTraderAccountId=client.account_id,symbolId=[info['symbol_id']]))
            matches=[s for s in response.symbol if s.symbolId==info['symbol_id']]
            if len(matches)!=1:raise ValueError('missing or duplicate symbol response')
            records.append({'requested_pair':pair,'broker_symbol':name,'record':schedule_record(matches[0],name)})
        except Exception as exc:failures.append({'pair':pair,'error_type':type(exc).__name__})
    document={'schema_version':'teacher_symbol_schedules_v1','retrieved_at':utc(retrieved_at or datetime.now(timezone.utc)).isoformat(),'status':'CURRENT_SCHEDULE_EVIDENCE' if not failures else 'PARTIAL' if records else 'FAILED','certification':'NOT_HISTORICAL_CALENDAR_CERTIFICATION','semantics':'Raw provider fields only; weekday origin, inclusive endpoints, timezone history and historical applicability unresolved','symbols':records,'failures':failures}
    directory=Path(out);directory.mkdir(parents=True,exist_ok=True);path=directory/'symbol_schedules.json'
    raw=(json.dumps(document,indent=2)+'\n').encode();path.write_bytes(raw)
    (directory/'symbol_schedules.sha256').write_text(sha256(raw).hexdigest()+'\n')
    return document


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--metadata',required=True);p.add_argument('--out',required=True);p.add_argument('--pairs',nargs='+',default=['ALL']);a=p.parse_args(argv)
    metadata=json.loads(Path(a.metadata).read_text());selected={s.strip().upper() for t in a.pairs for s in t.split(',') if s.strip()}
    if not selected or ('ALL' in selected and selected!={'ALL'}) or ('ALL' not in selected and selected-set(metadata)):p.error('invalid pair selection')
    if selected!={'ALL'}:metadata={k:v for k,v in metadata.items() if k in selected}
    if not metadata:p.error('empty metadata selection')
    directory=Path(a.out);directory.mkdir(parents=True,exist_ok=True);status_path=directory/'schedule_acquisition_status.json'
    status={'status':'STARTING'};status_path.write_text(json.dumps(status)+'\n');client=None
    try:
        client=HistoricalClient();client.connect();client.app_auth();client.account_auth()
    except Exception as exc:
        status={'status':'AUTH_OR_CONNECTION_FAILED','error_type':type(exc).__name__};status_path.write_text(json.dumps(status)+'\n')
        if client is not None:client.close()
        return 1
    try:
        result=collect_symbol_schedules(client,metadata,a.out)
        status={'status':result['status'],'symbols':len(result['symbols']),'failures':len(result['failures'])};status_path.write_text(json.dumps(status)+'\n')
        return 0 if not result['failures'] else 1
    finally:client.close()

if __name__=='__main__':raise SystemExit(main())
