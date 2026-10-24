"""Offline collection boundaries: fake client only, no credential/network use."""
from types import SimpleNamespace
from decimal import Decimal
import gzip
import json
import pytest
from bishop.collect_teacher_data import build_plan, exact_prices, collect_job, HistoricalClient, ReadOnlySettings
from ctrader.framing import oa


def test_real_fixture_inventory_and_required_resolutions():
    plan=build_plan(json.load(open('tests/bishop_examples.json')))
    assert len(plan['inventory'])==40
    assert {i['tf'] for i in plan['inventory']} >= {'M30','M45','H3'}
    assert {j['base_tf'] for j in plan['jobs']}=={'M5','H1'}
    planned={i for j in plan['jobs'] for i in j['case_ids']}
    assert planned=={i['id'] for i in plan['inventory'] if i['chart_snapshot_date']}
    assert all(i['clock_readiness']=='UNRESOLVED_SETUP_FILL_CLOCKS' for i in plan['inventory'])
    with pytest.raises(ValueError):build_plan({'examples':[]},34)


def test_raw_integer_protocol_precision_and_frozen_snapshot(tmp_path):
    tb=SimpleNamespace(low=1234567890,deltaOpen=12,deltaHigh=90,deltaClose=34,utcTimestampInMinutes=29453760)
    assert exact_prices(tb)[0]==Decimal('12345.67902')
    class Fake:
        account_id=7;env='demo'
        def symbol(self,name): return {'name':name,'symbol_id':9,'digits':5,'pip_position':4}
        def _hist_request(self,msg):
            assert isinstance(msg,oa.ProtoOAGetTrendbarsReq)
            return SimpleNamespace(trendbar=[tb],hasMore=False)
    job={'id':'job','pair':'X','base_tf':'M5','start':'2026-01-01T00:00:00Z','end':'2026-01-02T00:00:00Z','case_ids':['case']}
    # derive the fake timestamp from the declared window rather than wall time
    from bishop.v2.types import utc
    tb.utcTimestampInMinutes=int(utc(job['start']).timestamp())//60
    meta={'broker_symbol':'X','calendar_id':'24x7_utc_v1','anchor_id':'utc_epoch_v1','calendar_version':'declared_v1','asset_class':'synthetic_test'}
    result=collect_job(Fake(),job,meta,tmp_path,retrieved_at='2026-10-24T00:00:00Z')
    from pathlib import Path
    assert '12345.67902' in gzip.decompress(Path(result['path']).read_bytes()).decode()
    m=json.loads(Path(result['manifest']).read_text())
    assert m['coverage_status']=='NOT_CALENDAR_VALIDATED'
    assert m['raw_collection_status']=='RAW_COLLECTED_UNVALIDATED'
    assert m['chunks'][0]['completeness']=='UNVALIDATED_NO_PAGINATION_FLAG'
    assert m['zero_volume_rows']==1
    assert 'volume' in gzip.decompress(Path(result['path']).read_bytes()).decode().splitlines()[0]
    assert m['price_basis']=='BID' and m['retrieved_at'].startswith('2026-10-24')
    with pytest.raises(FileExistsError):collect_job(Fake(),job,meta,tmp_path)


def test_collector_never_refreshes_writes_or_sends_orders():
    client=HistoricalClient(settings=SimpleNamespace(get=lambda *a:None))
    with pytest.raises(RuntimeError):client._refresh()
    with pytest.raises(RuntimeError):client.settings.set('ctrader_access_token','changed')
    with pytest.raises(RuntimeError):client.request(oa.ProtoOANewOrderReq())
    with pytest.raises(RuntimeError):client.account_auth()


def test_cli_auth_failure_redacts_and_partial_jobs_continue(tmp_path,monkeypatch):
    import bishop.collect_teacher_data as module
    fixture=tmp_path/'fixtures.json';fixture.write_text(json.dumps({'examples':[{'id':'a','pair':'X','tf':'H1','chart_snapshot_date':'2026-01-01'}]}))
    metadata=tmp_path/'meta.json';metadata.write_text(json.dumps({'X':{}}))
    args=['--fixtures',str(fixture),'--plan-out',str(tmp_path/'plan.json'),'--collect','--metadata',str(metadata),'--out',str(tmp_path/'data')]
    class Client:
        def connect(self):raise RuntimeError('secret token account123')
        def close(self):pass
    monkeypatch.setattr(module,'HistoricalClient',Client)
    assert module.main(args)==1
    status=(tmp_path/'data/acquisition_status.json').read_text()
    assert 'secret' not in status and 'account123' not in status
    assert json.loads(status)['status']=='AUTH_OR_CONNECTION_FAILED'
    class Ready(Client):
        def connect(self):pass
        def app_auth(self):pass
        def account_auth(self):pass
    monkeypatch.setattr(module,'HistoricalClient',Ready)
    calls=[]
    def collect(client,job,*_):
        calls.append(job['id'])
        if len(calls)==1:raise RuntimeError('private error')
        return {'path':'fake','manifest':'fake_manifest','sha256':'hash','rows':1}
    monkeypatch.setattr(module,'collect_job',collect)
    assert module.main(args)==1
    status=json.loads((tmp_path/'data/acquisition_status.json').read_text())
    assert len(calls)==2 and status['status']=='PARTIAL'
    assert [j['status'] for j in status['jobs']]==['FAILED','RAW_COLLECTED_UNVALIDATED']
    assert 'private' not in json.dumps(status)


def test_pair_selection_all_comma_and_invalid_before_auth(tmp_path,monkeypatch):
    import bishop.collect_teacher_data as module
    fixture=tmp_path/'fixtures.json';fixture.write_text(json.dumps({'examples':[{'id':p,'pair':p,'tf':'H1','chart_snapshot_date':'2026-01-01'} for p in ('X','Y')]}))
    metadata=tmp_path/'meta.json';metadata.write_text(json.dumps({'X':{},'Y':{}}))
    args=['--fixtures',str(fixture),'--plan-out',str(tmp_path/'plan.json'),'--collect','--metadata',str(metadata),'--out',str(tmp_path/'data')]
    connections=[]
    class Client:
        def connect(self):connections.append(True)
        def app_auth(self):pass
        def account_auth(self):pass
        def close(self):pass
    monkeypatch.setattr(module,'HistoricalClient',Client)
    pairs=[]
    monkeypatch.setattr(module,'collect_job',lambda client,job,*_:pairs.append(job['pair']) or {'path':'fake'})
    assert module.main(args+['--pairs','ALL'])==0 and set(pairs)=={'X','Y'}
    pairs.clear()
    assert module.main(args+['--pairs','x,y'])==0 and set(pairs)=={'X','Y'}
    count=len(connections)
    for selection in ('UNKNOWN',',,,','ALL,X'):
        with pytest.raises(SystemExit):module.main(args+['--pairs',selection])
    assert len(connections)==count


def test_invalid_protocol_geometry_rejected():
    tb=SimpleNamespace(low=100,deltaOpen=20,deltaHigh=10,deltaClose=5)
    with pytest.raises(ValueError):exact_prices(tb)


def test_exploratory_annotations_preserve_fixture_clocks_and_bounded_jobs():
    fixture=json.load(open('tests/bishop_examples.json'));before=json.dumps(fixture,sort_keys=True)
    annotations=json.load(open('reports/teacher_clock_annotations.json'))
    result=build_plan(fixture,clock_annotations=annotations,annotations_only=True)
    assert json.dumps(fixture,sort_keys=True)==before
    assert result['plan_scope']=='ANNOTATED_EXPLORATORY_ONLY'
    assert len(result['jobs'])==8
    for job in result['jobs']:
        assert job['exploratory_case_ids']==job['case_ids']
        assert job['clock_annotations']
    native=next(i for i in result['inventory'] if i['id']=='video-entries5-native-t1410-eurusd')
    assert native['chart_snapshot_date'] is None and native['setup_time'] is None and native['fill_time'] is None
    assert native['clock_readiness']=='UNRESOLVED_SETUP_FILL_CLOCKS'
