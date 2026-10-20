import json
import pytest
from slk import research_finalize as f


def state(tmp_path,count=7):
    tasks=[f'EURUSD/window-{i:02d}/native/ledger.sqlite' for i in range(count)]
    for task in tasks:
        p=tmp_path/task;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
    path=tmp_path/'state.json'
    value=dict(source_run='123',tasks=tasks,cursor=0,slices=0,status='pending',consecutive_errors=0,errors=[])
    f.save(value,path);return path


def test_slice_saves_and_next_slice_only_processes_unfinished(tmp_path):
    path=state(tmp_path);calls=[]
    def publish(p,**kw):calls.append(str(p));return 5
    a=f.advance(tmp_path,'123',path,publisher=publish)
    assert a['cursor']==4 and a['status']=='pending'
    b=f.advance(tmp_path,'123',path,publisher=publish)
    assert b['cursor']==7 and b['status']=='complete'
    assert len(calls)==len(set(calls))==7


def test_interrupted_ledger_is_retried_without_replaying_study(tmp_path):
    path=state(tmp_path);calls=[]
    def publish(p,**kw):
        calls.append(str(p))
        if len(calls)==2:raise TimeoutError()
        return 5
    a=f.advance(tmp_path,'123',path,publisher=publish)
    assert a['cursor']==1
    b=f.advance(tmp_path,'123',path,publisher=publish)
    assert b['cursor']==5 and calls[1]==calls[2]


def test_storage_cap_stops_chain_and_preserves_progress(tmp_path):
    path=state(tmp_path)
    def blocked(*a,**k):raise f.PublicationBudgetExceeded()
    a=f.advance(tmp_path,'123',path,publisher=blocked)
    assert a['status']=='storage_blocked' and a['cursor']==0
    assert f.advance(tmp_path,'123',path,publisher=lambda *a,**k:pytest.fail())['status']=='storage_blocked'


def test_two_errors_stop_automatic_retry(tmp_path):
    path=state(tmp_path)
    def fail(*a,**k):raise RuntimeError('secret must not be recorded')
    assert f.advance(tmp_path,'123',path,publisher=fail)['status']=='pending'
    a=f.advance(tmp_path,'123',path,publisher=fail)
    assert a['status']=='failed' and 'secret' not in json.dumps(a)


def test_invalid_checkpoint_cannot_skip_tasks_or_escape_root(tmp_path):
    path=state(tmp_path);a=json.loads(path.read_text());a['tasks']=['../bad/ledger.sqlite'];f.save(a,path)
    with pytest.raises(ValueError):f.advance(tmp_path,'123',path)


def test_completed_state_never_starts_more_work(tmp_path):
    path=state(tmp_path,1);f.advance(tmp_path,'123',path,publisher=lambda *a,**k:0)
    a=f.advance(tmp_path,'123',path,publisher=lambda *a,**k:pytest.fail())
    assert a['status']=='complete'


def test_plan_creates_analysis_before_database_work(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);root=tmp_path/'history-results';root.mkdir()
    report=dict(pair='EURUSD',status='complete',planned_windows=1)
    d=root/'EURUSD';d.mkdir();(d/'history-report.json').write_text(json.dumps(report))
    for kind in ('native','scenarios'):
        p=d/'window-00'/kind;p.mkdir(parents=True);(p/'ledger.sqlite').touch()
    monkeypatch.setattr(f,'aggregate',lambda root:{'done':True})
    a,pair=f.plan(root,'123',expected_pairs=['EURUSD'])
    assert pair=='EURUSD' and a['analysis_status']=='complete'
    assert json.loads((tmp_path/'history-summary.json').read_text())['analysis']['done']


def test_plan_rejects_missing_window_file(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);d=tmp_path/'history-results/EURUSD';d.mkdir(parents=True)
    (d/'history-report.json').write_text(json.dumps(dict(pair='EURUSD',status='complete',planned_windows=1)))
    with pytest.raises(ValueError,match='ledger files'):
        f.plan(tmp_path/'history-results','123',expected_pairs=['EURUSD'])
