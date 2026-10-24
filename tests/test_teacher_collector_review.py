"""Independent collector boundaries using local fakes; no credentials/network."""
import csv
import gzip
import io
import json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
import bishop.collect_teacher_data as collector
from ctrader import tokens
from ctrader.framing import oa

T=datetime(2026,1,5,tzinfo=timezone.utc)


def test_borrowed_client_refuses_rotation_and_nonhistorical_requests(monkeypatch):
    backing=tokens.MemorySettings({'ctrader_access_token':'fake_access'},borrowed=True)
    client=collector.HistoricalClient(env='demo',client_id='fake',client_secret='fake',settings=backing)
    with pytest.raises(RuntimeError):client.settings.set('ctrader_access_token','changed')
    with pytest.raises(RuntimeError):client._refresh()
    with pytest.raises(RuntimeError):client.request(oa.ProtoOANewOrderReq())
    monkeypatch.setattr(tokens,'refresh_tokens',lambda *a,**k:pytest.fail('refresh called'))
    def expired(access):raise RuntimeError('expired borrowed token')
    monkeypatch.setattr(client,'_account_auth',expired)
    with pytest.raises(RuntimeError,match='expired borrowed token'):client.account_auth()
    assert backing.get('ctrader_access_token')=='fake_access'


def setup_cli(tmp_path,monkeypatch):
    fixtures=tmp_path/'cases.json'
    fixtures.write_text(json.dumps({'examples':[dict(id=p,pair=p,tf='H1',chart_snapshot_date='2026-01-05')
                                               for p in ('EURGBP','USDCAD')]}))
    metadata=tmp_path/'metadata.json';metadata.write_text(json.dumps({'EURGBP':{},'USDCAD':{}}))
    calls=[]
    class Client:
        def connect(self):calls.append('AUTH_CONNECT')
        def app_auth(self):pass
        def account_auth(self):pass
        def close(self):pass
    monkeypatch.setattr(collector,'HistoricalClient',Client)
    def collect(client,job,*a,**k):
        calls.append(job['pair'])
        return dict(path='fake',manifest='fake',sha256='fake',rows=1)
    monkeypatch.setattr(collector,'collect_job',collect)
    args=['--collect','--fixtures',str(fixtures),'--metadata',str(metadata),
          '--plan-out',str(tmp_path/'plan.json'),'--out-dir',str(tmp_path/'out'),
          '--context-days','35','--forward-days','0']
    return args,calls


@pytest.mark.parametrize('selection,expected',[('ALL',{'EURGBP','USDCAD'}),('EURGBP,USDCAD',{'EURGBP','USDCAD'})])
def test_workflow_pair_selection_collects_requested_jobs(tmp_path,monkeypatch,selection,expected):
    args,calls=setup_cli(tmp_path,monkeypatch)
    assert collector.main(args+['--pairs',selection])==0
    assert set(calls)-{'AUTH_CONNECT'}==expected
    assert len([x for x in calls if x!='AUTH_CONNECT'])==4


def test_unknown_pair_rejected_before_authentication(tmp_path,monkeypatch):
    args,calls=setup_cli(tmp_path,monkeypatch)
    with pytest.raises((SystemExit,ValueError)):
        collector.main(args+['--pairs','NOT_A_PAIR'])
    assert not calls


def test_protocol_prices_remain_exact_without_account_data_in_manifest(tmp_path):
    info=dict(name='EURGBP',symbol_id=11,digits=5,pip_position=4)
    tb=SimpleNamespace(low=123456,deltaOpen=1,deltaHigh=9,deltaClose=5,
                       utcTimestampInMinutes=int(T.timestamp()/60))
    class Client:
        account_id=88888888
        env='demo'
        def symbol(self,name):return info
        def _hist_request(self,request):return SimpleNamespace(trendbar=(tb,))
    job=dict(id='raw',pair='EURGBP',base_tf='H1',start=T.isoformat(),
             end=(T+timedelta(hours=1)).isoformat(),case_ids=['source_plan'])
    metadata=dict(broker_symbol='EURGBP',calendar_id='fx_ny_v1',anchor_id='ny17_wall_v2',
                  calendar_version='declared',asset_class='FX')
    output=collector.collect_job(Client(),job,metadata,tmp_path,retrieved_at=T+timedelta(days=1))
    with gzip.open(output['path'],'rt') as stream:row=next(csv.DictReader(stream))
    assert tuple(row[k] for k in ('open','high','low','close'))==('1.23457','1.23465','1.23456','1.23461')
    text=open(output['manifest']).read()
    assert '88888888' not in text and 'access_token' not in text and 'refresh_token' not in text
    assert json.loads(text)['coverage_status']!='COMPLETE'


def test_failed_job_is_nonzero_partial_and_exception_text_redacted(tmp_path,monkeypatch):
    args,calls=setup_cli(tmp_path,monkeypatch)
    def collect(client,job,*a,**k):
        if job['pair']=='USDCAD':raise RuntimeError('SECRET_ACCOUNT_TOKEN')
        return dict(path='fake',manifest='fake',sha256='fake',rows=1)
    monkeypatch.setattr(collector,'collect_job',collect)
    assert collector.main(args+['--pairs','EURGBP','USDCAD'])==1
    text=(tmp_path/'out'/'acquisition_status.json').read_text();status=json.loads(text)
    assert status['status']=='PARTIAL' and status['failed_jobs']==2 and status['collected_jobs']==2
    assert 'SECRET_ACCOUNT_TOKEN' not in text
