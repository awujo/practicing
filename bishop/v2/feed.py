"""Local frozen CSV ingestion; no acquisition or credential access."""
import csv
import gzip
import json
from pathlib import Path
from hashlib import sha256
from datetime import timedelta, datetime, timezone
from .types import Instrument, Bar, utc, stable_id
from .aggregation import minutes, expected_slots, is_open


def load_feed(path, manifest, as_of, history_start=None):
    if isinstance(manifest,(str,Path)): manifest=json.loads(Path(manifest).read_text())
    required=('symbol','tick_size','distance_unit','calendar_id','anchor_id','price_basis','source_id','venue','base_tf')
    if any(k not in manifest for k in required): raise ValueError('manifest requires '+', '.join(required))
    inst=Instrument(**{k:manifest[k] for k in required if k!='base_tf'})
    tf=manifest['base_tf']; n=minutes(tf)
    if n is None: raise ValueError('intraday base feed required')
    calendar=manifest.get('calendar',inst.calendar_id); clock=utc(as_of)
    raw=Path(path).read_bytes()
    expected_hash=manifest.get('sha256') or manifest.get('file_sha256')
    if expected_hash and sha256(raw).hexdigest()!=expected_hash: raise ValueError('feed hash mismatch')
    try:
        decoded=gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') or str(path).endswith('.gz') else raw
        rows=list(csv.DictReader(decoded.decode('utf-8-sig').splitlines()))
    except (OSError, EOFError, UnicodeDecodeError) as exc:
        raise ValueError('invalid CSV/gzip input') from exc
    bars=[]; previous=None; segment=0; missing=[]
    for row in rows:
        start=utc(row.get('start') or row.get('time') or next(iter(row.values())))
        end=utc(row['end']) if row.get('end') else start+timedelta(minutes=n)
        if end-start!=timedelta(minutes=n): raise ValueError('incorrect base duration')
        if (start.timestamp()/60)%n: raise ValueError('base starts must be UTC duration aligned')
        if previous is not None and start<previous.end: raise ValueError('unordered, duplicate or overlapping input')
        if not is_open(start,calendar): raise ValueError('input outside declared calendar')
        if previous is not None:
            gap=list(expected_slots(previous.end,start,tf,calendar))
            if gap: missing.extend(gap); segment+=1
        b=Bar(inst.symbol,tf,start,end,*(inst.to_ticks(row[k]) for k in ('open','high','low','close')),utc(row['available_at']) if row.get('available_at') else end,inst.source_id,str(segment))
        bars.append(b); previous=b
    lower=utc(history_start) if history_start else (bars[0].start if bars else clock)
    if lower>clock: raise ValueError('history_start after as_of')
    selected=tuple(b for b in bars if b.start>=lower and b.available_at<=clock)
    if (lower.timestamp()/60)%n: raise ValueError('history_start must align to base interval')
    horizon=datetime.fromtimestamp(int(clock.timestamp()//(n*60))*(n*60),timezone.utc)
    wanted=set(expected_slots(lower,horizon,tf,calendar)); present={b.start for b in selected}
    absent=sorted(wanted-present)
    coverage={'status':'COMPLETE' if not absent else 'INCOMPLETE','start':lower.isoformat(),'end':horizon.isoformat(),'expected_slots':len(wanted),'present_slots':len(wanted&present),'missing_slots':len(absent),'missing':[x.isoformat() for x in absent], 'calendar':calendar,'base_tf':tf,'anchor':inst.anchor_id,'metadata':{k:manifest[k] for k in ('provider','asset_class','calendar_version','anchor_version') if k in manifest}}
    hashes={'sha256':sha256(raw).hexdigest(),'manifest':stable_id('manifest',manifest),'source_id':inst.source_id}
    return {'instrument':inst,'bars':selected,'coverage':coverage,'hashes':hashes,'manifest':manifest}
