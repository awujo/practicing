from datetime import datetime
import gzip
import json
import pytest
from slk import research_archive as A


def row(payload="quotes ' \\ newlines\n☃ SQL ; DROP TABLE bias;", **extra):
    return dict(run_id='a'*64,kind='events',record_id='b'*64,payload_sha256=A.sha(payload.encode()),
                payload=payload,created_at=datetime(2026,10,22,8,0,0),**extra)


def archive(tmp_path, rows=None):
    rows=rows or [row()]
    p=tmp_path/('a'*64+'.sql.gz')
    with gzip.open(p,'wt',encoding='utf-8') as f:
        f.write(A.HEADER)
        for r in rows: f.write(A.PREFIX+','.join(A.sql_value(r[k]) for k in A.COLUMNS)+');\n')
    m=dict(format=1,table='research_records',rows=len(rows),payload_bytes=sum(len(r['payload'].encode()) for r in rows),
           files=[dict(file=p.name,run_id='a'*64,rows=len(rows),sha256=A.sha(p.read_bytes()))])
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    return p


def test_sql_roundtrip_special_characters_and_timestamps(tmp_path):
    p=archive(tmp_path)
    restored=list(A.read_rows(p))[0]
    assert restored['payload']==row()['payload']
    assert restored['created_at']=='2026-10-22 08:00:00'
    assert list(A.verified_files(tmp_path))[0][1][0]==restored


def test_corrupt_archive_and_wrong_paths_refused(tmp_path):
    p=archive(tmp_path)
    p.write_bytes(p.read_bytes()+b'corrupt')
    with pytest.raises(ValueError): list(A.verified_files(tmp_path))
    archive(tmp_path)
    m=json.loads((tmp_path/'manifest.json').read_text());m['files'][0]['file']='../../bias.sql.gz'
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError): list(A.verified_files(tmp_path))


def test_prune_requires_verified_restore_before_connection(tmp_path):
    archive(tmp_path)
    def forbidden(): pytest.fail('must not connect without restore proof')
    with pytest.raises(FileNotFoundError): A.prune(tmp_path,forbidden)
    (tmp_path/'restore-verified.json').write_text(json.dumps(dict(manifest_sha256='bad',rows=1)))
    with pytest.raises(ValueError): A.prune(tmp_path,forbidden)


def test_restore_rejects_production_database(tmp_path):
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def execute(self,sql):assert sql=='SELECT DATABASE() AS name'
        def fetchone(self):return {'name':'production'}
    class Conn:
        def cursor(self):return Cursor()
        def close(self):pass
    with pytest.raises(ValueError): A.restore_verify(tmp_path,Conn())


def test_mysql_export_restore_and_hash_guarded_prune(tmp_path):
    import os
    if os.environ.get('SLK_ARCHIVE_TEST_MYSQL') != '1':
        pytest.skip('requires disposable archive_verify MySQL service')
    import pymysql
    import pymysql.cursors
    def connect():
        return pymysql.connect(host='127.0.0.1',port=3306,user='root',password='local-test-only',
                               database='archive_verify',charset='utf8mb4',autocommit=True,
                               cursorclass=pymysql.cursors.DictCursor)
    r=row()
    conn=connect()
    with conn.cursor() as c:
        c.execute(A.DDL)
        c.execute('TRUNCATE TABLE research_records')
        c.execute(A.PREFIX+','.join(A.sql_value(r[k]) for k in A.COLUMNS)+');')
    conn.close()
    root=tmp_path/'first'
    A.export(root,connect)
    conn=connect()
    with conn.cursor() as c:c.execute('TRUNCATE TABLE research_records')
    conn.close()
    A.restore_verify(root,connect())
    conn=connect()
    with conn.cursor() as c:c.execute("UPDATE research_records SET payload='changed'")
    conn.close()
    with pytest.raises(ValueError,match='changed'): A.prune(root,connect)
    conn=connect()
    with conn.cursor() as c:
        c.execute('UPDATE research_records SET payload=%s',(r['payload'],))
        extra={**r,'record_id':'c'*64}
        c.execute(A.PREFIX+','.join(A.sql_value(extra[k]) for k in A.COLUMNS)+');')
    conn.close()
    result=A.prune(root,connect)
    assert result['deleted_rows']==1 and result['remaining_research_rows']==1
    assert not result['empty_table_reclaimed']
    second=tmp_path/'second'
    A.export(second,connect)
    conn=connect()
    with conn.cursor() as c:c.execute('TRUNCATE TABLE research_records')
    conn.close()
    A.restore_verify(second,connect())
    result=A.prune(second,connect)
    assert result['deleted_rows']==1 and result['remaining_research_rows']==0
    assert result['empty_table_reclaimed']
