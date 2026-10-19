"""Publish immutable research-only records to the existing MySQL. Never apply live schema."""
import json
from pathlib import Path
import sqlite3
from .research import digest, encoded, MAX_OUTPUT


def publish(path, connection_factory=None):
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
        remote=connection_factory()
        try:
            with remote.cursor() as c:
                c.execute('''CREATE TABLE IF NOT EXISTS research_records (
                    run_id CHAR(64) NOT NULL, kind VARCHAR(16) NOT NULL, record_id CHAR(64) NOT NULL,
                    payload_sha256 CHAR(64) NOT NULL, payload LONGTEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(run_id,kind,record_id))''')
                for kind,rid,payload in records:
                    hashed=digest(payload.encode())
                    c.execute('INSERT IGNORE INTO research_records (run_id,kind,record_id,payload_sha256,payload) VALUES (%s,%s,%s,%s,%s)',
                              (identity,kind,rid,hashed,payload))
                    c.execute('SELECT payload_sha256 FROM research_records WHERE run_id=%s AND kind=%s AND record_id=%s',(identity,kind,rid))
                    got=c.fetchone()
                    if got['payload_sha256']!=hashed:
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
