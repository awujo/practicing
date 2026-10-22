"""Archive only research_records. Export, restore-verify, then hash-matched pruning.

No live/user tables, broker connections, or messaging. SQL payloads use hex literals
so quotes, newlines and SQL-mode differences cannot change research data.
"""
import argparse
import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

COLUMNS = ('run_id','kind','record_id','payload_sha256','payload','created_at')
DDL = '''CREATE TABLE IF NOT EXISTS research_records (
run_id CHAR(64) NOT NULL, kind VARCHAR(16) NOT NULL, record_id CHAR(64) NOT NULL,
payload_sha256 CHAR(64) NOT NULL, payload LONGTEXT NOT NULL,
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
PRIMARY KEY(run_id,kind,record_id)) CHARACTER SET utf8mb4;'''
HEADER = "SET NAMES utf8mb4;\nSET time_zone = '+00:00';\n" + DDL + '\n'
PREFIX = 'INSERT INTO research_records (' + ','.join(COLUMNS) + ') VALUES ('


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sql_value(value):
    if value is None:
        return 'NULL'
    if isinstance(value, datetime):
        value = value.strftime('%Y-%m-%d %H:%M:%S')
    return "X'" + str(value).encode('utf-8').hex() + "'"


def read_rows(path):
    """Parse only our exact archive grammar; never evaluate archive SQL in production."""
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        if f.read(len(HEADER)) != HEADER:
            raise ValueError('unrecognized research archive header')
        for line in f:
            if not line.startswith(PREFIX) or not line.endswith(');\n'):
                raise ValueError('invalid archive statement')
            parts = line[len(PREFIX):-3].split(',')
            if len(parts) != len(COLUMNS) or any(not re.fullmatch(r"X'[0-9a-f]*'|NULL", x) for x in parts):
                raise ValueError('invalid archive values')
            row = {k: None if v == 'NULL' else bytes.fromhex(v[2:-1]).decode('utf-8')
                   for k, v in zip(COLUMNS, parts)}
            if sha(row['payload'].encode()) != row['payload_sha256']:
                raise ValueError('research payload hash mismatch')
            yield row


def export(root, connect=None):
    from .db import connect as production_connect
    connect = connect or production_connect
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if (root/'manifest.json').exists():
        raise ValueError('archive already exists; choose a new directory')
    conn = connect()
    files, total, payload_bytes = [], 0, 0
    try:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='research_records'")
            if not c.fetchone()['n']:
                raise ValueError('no research_records table')
            c.execute('SELECT DISTINCT run_id FROM research_records ORDER BY run_id')
            runs = [r['run_id'] for r in c.fetchall()]
            for run in runs:
                if not re.fullmatch('[0-9a-f]{64}', run):
                    raise ValueError('unexpected research run ID')
                c.execute('SELECT '+','.join(COLUMNS)+' FROM research_records WHERE run_id=%s ORDER BY kind,record_id', (run,))
                rows = c.fetchall()
                path = root/(run+'.sql.gz')
                with gzip.open(path, 'wt', encoding='utf-8', compresslevel=9) as out:
                    out.write(HEADER)
                    for row in rows:
                        if sha(row['payload'].encode()) != row['payload_sha256']:
                            raise ValueError('database research payload hash mismatch')
                        out.write(PREFIX+','.join(sql_value(row[k]) for k in COLUMNS)+');\n')
                        payload_bytes += len(row['payload'].encode())
                if sum(1 for _ in read_rows(path)) != len(rows):
                    raise ValueError('export roundtrip row mismatch')
                files.append({'run_id':run, 'file':path.name, 'rows':len(rows), 'sha256':sha(path.read_bytes())})
                total += len(rows)
    finally:
        conn.close()
    manifest = {'format':1, 'table':'research_records', 'created_at':datetime.now(timezone.utc).isoformat(),
                'rows':total, 'payload_bytes':payload_bytes, 'files':files}
    (root/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (root/'README.md').write_text('Research database archive. One compressed SQL file per experiment run ID.\n'
        'Restore into a separate research database: gunzip -c <run-id>.sql.gz | mysql <database>\n'
        'UTC timestamps and UTF-8 payload bytes are preserved. manifest.json contains file hashes and row counts.\n'
        'Contains research data only; no user profiles, settings, live biases, entries, orders or credentials.\n')
    print(f'Exported {total} records / {len(files)} experiments / {payload_bytes} payload bytes', flush=True)
    return manifest


def verified_files(root):
    root = Path(root)
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest.get('table') != 'research_records' or manifest.get('format') != 1:
        raise ValueError('wrong archive format/table')
    total = 0
    for item in manifest['files']:
        if not re.fullmatch('[0-9a-f]{64}', item['run_id']) or item['file'] != item['run_id']+'.sql.gz':
            raise ValueError('invalid archive file path')
        path = root/item['file']
        if sha(path.read_bytes()) != item['sha256']:
            raise ValueError('archive file hash mismatch')
        rows = list(read_rows(path))
        if len(rows) != item['rows'] or any(r['run_id'] != item['run_id'] for r in rows):
            raise ValueError('archive count/run mismatch')
        keys = {(r['kind'],r['record_id']) for r in rows}
        if len(keys) != len(rows):
            raise ValueError('duplicate research archive key')
        total += len(rows)
        yield item, rows
    if total != manifest['rows']:
        raise ValueError('archive total mismatch')


def restore_verify(root, conn):
    """A separate disposable MySQL connection; production never runs archive statements."""
    restored = 0
    try:
        with conn.cursor() as c:
            c.execute('SELECT DATABASE() AS name')
            if c.fetchone()['name'] != 'archive_verify':
                raise ValueError('restore requires disposable archive_verify database')
            c.execute("SET time_zone = '+00:00'")
            c.execute(DDL)
            c.execute('SELECT COUNT(*) AS n FROM research_records')
            if c.fetchone()['n']:
                raise ValueError('restore database must be empty')
            for item, rows in verified_files(root):
                # Execute the actual exported SQL in the disposable verifier.
                with gzip.open(Path(root)/item['file'], 'rt', encoding='utf-8') as f:
                    f.read(len(HEADER))
                    for line in f:
                        c.execute(line)
                c.execute('SELECT '+','.join(COLUMNS)+' FROM research_records WHERE run_id=%s ORDER BY kind,record_id', (item['run_id'],))
                actual = c.fetchall()
                normalized = [{k: (v.strftime('%Y-%m-%d %H:%M:%S') if isinstance(v,datetime) else v)
                               for k,v in row.items()} for row in actual]
                if normalized != rows:
                    raise ValueError('restored SQL content differs from export')
                restored += len(rows)
        conn.commit()
    finally:
        conn.close()
    report = {'rows':restored,'manifest_sha256':sha((Path(root)/'manifest.json').read_bytes()),
              'verified_at':datetime.now(timezone.utc).isoformat()}
    (Path(root)/'restore-verified.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'Restore verified {restored} rows in disposable MySQL', flush=True)


def prune(root, connect=None):
    """Delete only archived immutable rows; preserve any newer/unarchived records."""
    from .db import connect as production_connect
    connect = connect or production_connect
    root = Path(root)
    proof = json.loads((root/'restore-verified.json').read_text())
    manifest = json.loads((root/'manifest.json').read_text())
    if proof['manifest_sha256'] != sha((root/'manifest.json').read_bytes()) or proof['rows'] != manifest['rows']:
        raise ValueError('missing/mismatched restore verification')
    # Validate every file before the first deletion, including archive-total validation.
    for _ in verified_files(root): pass
    deleted = 0
    conn = connect()
    try:
        conn.autocommit(False)
        with conn.cursor() as c:
            c.execute("SELECT GET_LOCK('slk_research_records',10) AS acquired")
            if c.fetchone()['acquired'] != 1:
                raise TimeoutError('research publication lock unavailable')
            for item, rows in verified_files(root):
                c.execute('SELECT run_id,kind,record_id,payload_sha256,SHA2(payload,256) AS actual_sha '
                          'FROM research_records WHERE run_id=%s FOR UPDATE', (item['run_id'],))
                current = {(r['kind'],r['record_id']):r for r in c.fetchall()}
                for row in rows:
                    found = current.get((row['kind'],row['record_id']))
                    if found and (found['payload_sha256'] != row['payload_sha256'] or found['actual_sha'] != row['payload_sha256']):
                        raise ValueError('database record changed since export; refusing deletion')
                keys = [(r['run_id'],r['kind'],r['record_id'],r['payload_sha256']) for r in rows]
                for start in range(0,len(keys),500):
                    chunk = keys[start:start+500]
                    marks = ','.join(['(%s,%s,%s,%s)'] * len(chunk))
                    deleted += c.execute('DELETE FROM research_records WHERE '
                                         '(run_id,kind,record_id,payload_sha256) IN ('+marks+')',
                                         [value for key in chunk for value in key])
                conn.commit()
            c.execute('SELECT COUNT(*) AS n FROM research_records')
            remaining = int(c.fetchone()['n'])
            conn.commit()
            if remaining == 0:
                # Shared MySQL advisory lock and workflow concurrency prevent publisher races.
                # Empty-table TRUNCATE releases the research table file for other tables to use.
                c.execute('TRUNCATE TABLE research_records')
            conn.commit()
        report = {'deleted_rows':deleted,'remaining_research_rows':remaining,
                  'archived_payload_bytes':manifest['payload_bytes'], 'empty_table_reclaimed':remaining==0}
        print(json.dumps(report), flush=True)
        return report
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['export','restore-verify','prune'])
    p.add_argument('directory')
    a = p.parse_args()
    if a.mode == 'export': export(a.directory)
    elif a.mode == 'prune':
        report=prune(a.directory)
        Path('research-prune-result.json').write_text(json.dumps(report,indent=2)+'\n')
    else:
        import pymysql
        import pymysql.cursors
        c=pymysql.connect(host='127.0.0.1',port=3306,user='root',password='local-test-only',
                          database='archive_verify',charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor)
        restore_verify(a.directory,c)


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        raise SystemExit('Research archive failed: '+type(exc).__name__) from None
