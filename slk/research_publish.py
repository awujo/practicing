"""Publish immutable research-only records to the existing MySQL. Never apply live schema."""
import json
from pathlib import Path
import sqlite3
import time
from .research import digest, encoded, MAX_OUTPUT


class PublicationBudgetExceeded(ValueError):
    pass


def publish(path, connection_factory=None, max_total_bytes=None, deadline=None):
    if Path(path).stat().st_size > MAX_OUTPUT:
        raise ValueError('ledger exceeds 10 MiB')
    local=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        identity, manifest=local.execute('SELECT identity,manifest FROM meta WHERE id=1').fetchone()
        # SQL identifiers are constants; payloads/ids are parameter-bound.
        records=[('manifest',identity,manifest)]
        for table in ('events','observations'):
            records.extend((table,k,v) for k,v in local.execute('SELECT '+('id' if table=='events' else 'event_id')+',payload FROM '+table))
        for eid,policy,yes in local.execute('SELECT event_id,policy,accepted FROM decisions'):
            records.append(('decisions',digest(encoded([eid,policy])),encoded({'event_id':eid,'policy':policy,'accepted':bool(yes)}).decode()))
        tables={row[0] for row in local.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'entry_trials' in tables:
            records.extend(('entry_trials',digest(encoded([eid,variant])),payload)
                           for eid,variant,payload in local.execute('SELECT event_id,variant,payload FROM entry_trials'))
        if 'scenarios' in tables:
            records.extend(('scenarios',k,v) for k,v in local.execute('SELECT id,payload FROM scenarios'))
        if 'discovery_findings' in tables:
            records.extend(('discovery',digest(payload.encode()),payload) for k,payload in local.execute('SELECT id,payload FROM discovery_findings'))
        if 'steps' in tables:
            steps=list(local.execute('SELECT cutoff,state FROM steps'))
            progress=local.execute('SELECT completed FROM progress WHERE id=1').fetchone()[0]
            checkpoint=encoded({'steps':steps,'completed':progress}).decode()
            records.append(('checkpoint',digest(checkpoint.encode()),checkpoint))
        if len(records)>20000:
            raise ValueError('publication exceeds 20000 records')
        if connection_factory is None:
            from .db import connect
            connection_factory=connect
        def check_deadline():
            if deadline is not None and time.monotonic()>=deadline:raise TimeoutError('publication slice elapsed')
        check_deadline()
        remote=connection_factory()
        try:
            with remote.cursor() as c:
                c.execute('''CREATE TABLE IF NOT EXISTS research_records (
                    run_id CHAR(64) NOT NULL, kind VARCHAR(16) NOT NULL, record_id CHAR(64) NOT NULL,
                    payload_sha256 CHAR(64) NOT NULL, payload LONGTEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(run_id,kind,record_id))''')
                check_deadline()
                c.execute('SELECT kind,record_id,payload_sha256 FROM research_records WHERE run_id=%s',(identity,))
                stored={(r['kind'],r['record_id']):r['payload_sha256'] for r in c.fetchall()}
                if any((kind,rid) in stored and stored[(kind,rid)]!=digest(payload.encode()) for kind,rid,payload in records):
                    raise ValueError('immutable research record conflict')
                pending=[r for r in records if (r[0],r[1]) not in stored]
                if not pending:return len(records)
                total_bytes=0
                if max_total_bytes is not None:
                    if max_total_bytes<1:raise ValueError('positive research storage budget required')
                    c.execute('SELECT COALESCE(SUM(OCTET_LENGTH(payload)),0) AS bytes FROM research_records')
                    total_bytes=int(c.fetchone()['bytes'])
                for first in range(0,len(pending),100):
                    check_deadline()
                    chunk=pending[first:first+100]
                    rows=[(identity,kind,rid,digest(payload.encode()),payload) for kind,rid,payload in chunk]
                    if max_total_bytes is not None:
                        budget_ids=sorted({rid for _,rid,_ in chunk});budget_marks=','.join(['%s']*len(budget_ids))
                        c.execute('SELECT kind,record_id,payload_sha256 FROM research_records WHERE run_id=%s AND record_id IN ('+budget_marks+')',(identity,*budget_ids))
                        existing={(r['kind'],r['record_id']) for r in c.fetchall()}
                        added=sum(len(payload.encode()) for kind,rid,payload in chunk if (kind,rid) not in existing)
                        if total_bytes+added>max_total_bytes:raise PublicationBudgetExceeded('research payload storage budget exhausted')
                        total_bytes+=added
                    c.executemany('INSERT IGNORE INTO research_records (run_id,kind,record_id,payload_sha256,payload) VALUES (%s,%s,%s,%s,%s)',rows)
                    ids=sorted({rid for _,rid,_ in chunk})
                    marks=','.join(['%s']*len(ids))
                    c.execute('SELECT kind,record_id,payload_sha256 FROM research_records WHERE run_id=%s AND record_id IN ('+marks+')',(identity,*ids))
                    hashes={(row['kind'],row['record_id']):row['payload_sha256'] for row in c.fetchall()}
                    if any(hashes.get((kind,rid))!=digest(payload.encode()) for kind,rid,payload in chunk):
                        raise ValueError('immutable research record conflict')
            return len(records)
        finally:remote.close()
    finally:local.close()


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('ledgers',nargs='+');a=p.parse_args()
    try:
        for path in a.ledgers: print(f'Published {publish(path)} research records')
    except Exception as exc:
        # Do not log raw DB/broker errors or connection URLs.
        raise SystemExit(f'Research publication failed: {type(exc).__name__}')
