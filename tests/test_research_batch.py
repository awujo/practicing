import json
from pathlib import Path

import pytest

from slk import research_collect as c, research_batch as b, research_replay as r, research_publish as p


def test_pair_queue():
    all_pairs, selected=c.select('',0,4)
    assert len(all_pairs)==28 and selected==all_pairs[:4]
    assert c.select('',4,4)[1]==all_pairs[4:8]
    with pytest.raises(ValueError):c.select('EURUSD,EURUSD')
    with pytest.raises(ValueError):c.select('',0,5)


def manifest():
    return {'source':'ctrader','start':'2023-07-07T00:00Z','end':'2026-10-19T09:00Z',
            'evaluation_start':'2026-10-01T00:00Z','requested_pairs':['EURUSD','USDCHF'],
            'selected_pairs':['EURUSD'],'offset':0,'next_offset':1,
            'entries':[{'pair':'EURUSD','status':'ready','file':'EURUSD_H1_ctrader.csv.gz'}]}


def test_missing_pair_not_silently_counted(tmp_path,monkeypatch):
    m=manifest();m['entries'][0]={'pair':'EURUSD','status':'acquisition_failed'}
    (tmp_path/'batch.json').write_text(json.dumps(m))
    results=b.run(tmp_path,tmp_path/'out')
    assert results[0]['status']=='acquisition_failed'
    assert json.loads((tmp_path/'out'/'batch-report.json').read_text())['next_offset']==1


@pytest.mark.parametrize('mutation', ['source','pair','offset','file','dates'])
def test_manifest_integrity(tmp_path,mutation):
    m=manifest()
    if mutation=='source':m['source']='other'
    if mutation=='pair':m['entries'][0]['pair']='GBPUSD'
    if mutation=='offset':m['next_offset']=None
    if mutation=='file':m['entries'][0]['file']='../x'
    if mutation=='dates':m['evaluation_start']=m['start']
    (tmp_path/'batch.json').write_text(json.dumps(m))
    with pytest.raises(ValueError):b.run(tmp_path,tmp_path/'out')


class Cursor:
    def __init__(self):self.data={};self.selected=None;self.sql=[]
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def execute(self,sql,args=None):
        self.sql.append(sql)
        if sql.startswith('INSERT IGNORE'):self.data.setdefault(args[:3],args[3])
        if sql.startswith('SELECT'):self.selected=args
    def executemany(self,sql,rows):
        for row in rows:self.execute(sql,row)
    def fetchone(self):return {"acquired":1}
    def fetchall(self):
        run,*ids=self.selected
        return [{'kind':kind,'record_id':rid,'payload_sha256':v} for (runid,kind,rid),v in self.data.items() if runid==run and (not ids or rid in ids)]


class Remote:
    def __init__(self):self.c=Cursor()
    def cursor(self):return self.c
    def close(self):pass


def test_publication_idempotent_research_only(tmp_path):
    path=tmp_path/'ledger.sqlite'; local=r.connect(path)
    with local:
        local.execute('INSERT INTO meta VALUES (1,?,?)',('a'*64,'{}'))
        local.execute('INSERT INTO events VALUES (?,?)',('b'*64,'{"kind":"test"}'))
    local.close();remote=Remote()
    assert p.publish(path,lambda:remote)==3
    assert p.publish(path,lambda:remote)==3
    assert len(remote.c.data)==3
    assert all('research_records' in sql for sql in remote.c.sql)
    remote.c.data[('a'*64,'events','b'*64)]='tampered'
    with pytest.raises(ValueError,match='conflict'):p.publish(path,lambda:remote)


def test_scenario_publication_budget_is_checked_before_inserts(tmp_path):
    path=tmp_path/'ledger.sqlite';local=r.connect(path)
    local.execute('INSERT INTO meta VALUES (1,?,?)',('a'*64,'{}'))
    local.execute('CREATE TABLE scenarios(id TEXT PRIMARY KEY,payload TEXT)')
    local.execute('INSERT INTO scenarios VALUES(?,?)',('b'*64,'{"outcome":"observed"}'));local.commit();local.close()
    class BudgetCursor(Cursor):
        def __init__(self):super().__init__();self.bytes=0
        def execute(self,sql,args=None):
            if sql.startswith('INSERT IGNORE') and args[:3] not in self.data:self.bytes+=len(args[4].encode())
            super().execute(sql,args)
        def fetchone(self):return {'bytes':self.bytes,'acquired':1}
    remote=Remote();remote.c=BudgetCursor()
    with pytest.raises(ValueError,match='storage budget'):
        p.publish(path,lambda:remote,max_total_bytes=1)
    assert not remote.c.data
    assert p.publish(path,lambda:remote,max_total_bytes=1000)==3
    actual=remote.c.bytes
    assert any(kind=='scenarios' for _,kind,_ in remote.c.data)
    assert p.publish(path,lambda:remote,max_total_bytes=actual)==3
    assert remote.c.bytes==actual
