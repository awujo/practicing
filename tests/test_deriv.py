import json
import pandas as pd
import pytest
from slk import candles,deriv,instruments,live,store

RAW=dict(underlying_symbol='1HZ100V',underlying_symbol_name='Volatility 100 (1s) Index',pip_size=.01,
         market='synthetic_index',exchange_is_open=1,is_trading_suspended=0)


def test_catalogue_names_precision_and_existing_forex_pips():
    rows=deriv.catalogue([RAW,{**RAW,'underlying_symbol':'frxUSDJPY','market':'forex','pip_size':.001},
                          {**RAW,'underlying_symbol':'frxEURUSD','market':'forex','pip_size':.00001}])
    assert rows[0]['key']=='DV1HZ100V' and rows[0]['digits']==2 and rows[0]['pip']==.01
    assert rows[1]['pip']==.01 and rows[1]['digits']==3
    assert rows[2]['pip']==.0001 and rows[2]['digits']==5
    assert len(deriv.catalogue([RAW,{**RAW,'underlying_symbol':'x'*40},{**RAW,'pip_size':.25}]))==1


def test_public_socket_matching_errors_and_close(monkeypatch):
    monkeypatch.setattr(deriv.time,'sleep',lambda t:None)
    class Socket:
        def __init__(self):self.sent=[];self.closed=False
        def send(self,text):self.sent.append(json.loads(text))
        def recv(self):return json.dumps({'req_id':self.sent[-1]['req_id'],'active_symbols':[RAW]})
        def close(self):self.closed=True
    ws=Socket()
    with deriv.Feed(lambda *a,**kw:ws) as f:
        rows=f.prefetch()
        assert rows[0]['key']=='DV1HZ100V'
        assert not any('token' in x or 'authorize' in x for x in ws.sent)
    assert ws.closed


def test_bars_reject_bad_ohlc_and_exclude_out_of_window_and_partial():
    f=deriv.Feed();f.symbols={'DV1HZ100V':{'symbol':'1HZ100V'}}
    values=[dict(epoch=3600,open=1,high=2,low=.5,close=1.5),
            dict(epoch=7200,open=1,high=2,low=.5,close=1.5),
            dict(epoch=3700,open=1,high=2,low=.5,close=1.5)]
    f.request=lambda request:{'candles':values}
    assert f.bars('DV1HZ100V',3600,7200)==[(3600,1.,2.,.5,1.5)]
    values[0]['low']=4
    with pytest.raises(ValueError):f.bars('DV1HZ100V',3600,7200)


class FakeFeed:
    max_span=120*86400
    def __init__(self):self.calls=[]
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def prefetch(self,*a):return []
    def info(self,pair):return dict(deriv.catalogue([RAW])[0])
    def bars(self,pair,lo,hi):
        self.calls.append((pair,lo,hi))
        return [(t,100.,102.,99.,101.) for t in range(lo,hi,3600)]


def test_store_provider_metadata_closed_hours_and_no_fallback(tmp_path,monkeypatch):
    feed=FakeFeed();monkeypatch.setattr(deriv,'Feed',lambda:feed)
    monkeypatch.setattr(store,'_update_standard_all',lambda *a,**kw:pytest.fail('Deriv must not reach FX feed'))
    now=pd.Timestamp('2026-10-22 10:03Z')
    assert store.update_all(['DV1HZ100V'],now,days=10,root=str(tmp_path))=={}
    s=store.Pair('DV1HZ100V',str(tmp_path))
    assert s.src=='deriv' and s.sym['pip_position']==2
    assert instruments.pip('DV1HZ100V')==.01
    h=store.recent('DV1HZ100V',10,now,root=str(tmp_path))
    assert (h.index+pd.Timedelta(hours=1)<=now).all()
    assert (h.index.dayofweek>=5).any() # weekends preserved
    assert 'Deriv' in instruments.label('DV1HZ100V')


def test_stale_synthetic_data_stops_scan(tmp_path):
    class Stale(FakeFeed):
        def bars(self,pair,lo,hi):return []
    with pytest.raises(RuntimeError,match='stale scan'):
        store.update('DV1HZ100V',pd.Timestamp('2026-10-22 10:03Z'),days=2,root=str(tmp_path),feed=Stale())


def test_hourly_deriv_returns_final_month_frame(tmp_path):
    frame=store.hourly('DV1HZ100V',2026,2026,root=str(tmp_path),now=pd.Timestamp('2026-02-03T00:00Z'),feed=FakeFeed())
    assert isinstance(frame,pd.DataFrame) and frame.index.min()==pd.Timestamp('2026-01-01T00:00Z')
    assert frame.index.max()==pd.Timestamp('2026-01-31 23:00Z')


def test_native_utc_week_and_forming_boundaries_do_not_change_fx():
    idx=pd.date_range('2026-10-12',periods=7*24,freq='h',tz='UTC')
    h=pd.DataFrame(dict(open=1.,high=2.,low=.5,close=1.5),index=idx)
    with candles.market('DV1HZ100V'):
        assert candles.nominal_end(idx[0],'W')==pd.Timestamp('2026-10-19T00:00Z')
        assert live.drop_forming(h,'W',pd.Timestamp('2026-10-17 12:00Z')).empty
        assert len(live.drop_forming(h,'W',pd.Timestamp('2026-10-19T00:00Z')))==168
        assert candles._key(pd.DatetimeIndex(['2026-10-22T09:00Z']),'H4')[0]==pd.Timestamp('2026-10-22 08:00')
    assert not candles.UTC_MARKET.get()
    assert candles.nominal_end(pd.Timestamp('2026-10-11 21:00Z'),'W')==pd.Timestamp('2026-10-16 21:00Z')


def test_weekend_watchlist_union_only_continuous_deriv(monkeypatch):
    from argparse import Namespace
    from slk import db,tenancy
    monkeypatch.setenv('TELEGRAM_CHAT_ID','1')
    monkeypatch.setenv('GITHUB_EVENT_NAME','schedule')
    monkeypatch.setattr(db,'apply_schema',lambda:None)
    monkeypatch.setattr(db,'query',lambda *a:[])
    monkeypatch.setattr(db,'get_setting',lambda *a:'0')
    monkeypatch.setattr(db,'get_settings',lambda:{'pairs':'EURUSD,DV1HZ100V,DVFRXEURUSD'})
    got=[]
    monkeypatch.setattr(live,'prepare_candles',lambda pairs,now:got.append(pairs) or {})
    monkeypatch.setattr(live,'main',lambda *a,**kw:0)
    live.run_user_watchlists([],Namespace(pairs='',stories=''),pd.Timestamp('2026-10-24 12:00Z'))
    assert got==[['DV1HZ100V']]
    monkeypatch.setenv('GITHUB_EVENT_NAME','workflow_dispatch')
    live.run_user_watchlists([],Namespace(pairs='',stories=''),pd.Timestamp('2026-10-24 12:00Z'))
    assert got[-1]==['DV1HZ100V','DVFRXEURUSD','EURUSD']
    assert tenancy.USER.get() is None


def test_continuous_history_gaps_rejected():
    f=deriv.Feed();f.symbols={'DV1HZ100V':{'symbol':'1HZ100V','market':'synthetic_index'}}
    f.request=lambda request:{'candles':[dict(epoch=t,open=1,high=2,low=.5,close=1.5) for t in (3600,10800)]}
    with pytest.raises(ValueError,match='gap'):f.bars('DV1HZ100V',3600,14400)


def test_bad_symbol_never_gets_fx_fallback(tmp_path,monkeypatch):
    class Missing(FakeFeed):
        def info(self,pair):raise ValueError('not found')
    monkeypatch.setattr(deriv,'Feed',Missing)
    monkeypatch.setattr(store,'_update_standard_all',lambda *a,**kw:pytest.fail('no FX fallback'))
    assert 'DVBAD' in store.update_all(['DVBAD'],pd.Timestamp('2026-10-22T10:03Z'),days=1,root=str(tmp_path))


def test_gap_across_final_and_current_month_rejected_and_retried(tmp_path):
    class Gap(FakeFeed):
        def bars(self,pair,lo,hi):
            rows=super().bars(pair,lo,hi)
            return rows[1:] if pd.Timestamp(lo,unit='s',tz='UTC').month==10 else rows
    with pytest.raises(RuntimeError,match='hourly gap'):
        store.update('DV1HZ100V',pd.Timestamp('2026-10-22T10:03Z'),days=45,root=str(tmp_path),feed=Gap())
    p=store.Pair('DV1HZ100V',str(tmp_path))
    assert '2026-09' not in p.done_m
    repaired=store.update('DV1HZ100V',pd.Timestamp('2026-10-22T10:03Z'),days=45,root=str(tmp_path),feed=FakeFeed())
    assert (repaired.df.index.to_series().diff().dropna()==3600).all()


def test_rate_limit_retries_without_replaying_permanent_errors(monkeypatch):
    sleeps=[]
    monkeypatch.setattr(deriv.time,'sleep',sleeps.append)
    class Socket:
        def __init__(self,errors):self.errors=list(errors);self.sent=[]
        def send(self,text):self.sent.append(json.loads(text))
        def recv(self):
            code=self.errors.pop(0)
            return json.dumps({'req_id':self.sent[-1]['req_id'],**({'error':{'code':code}} if code else {'ok':1})})
    feed=deriv.Feed();feed.ws=Socket(['RateLimit','RateLimit',None])
    assert feed.request({'active_symbols':'brief'})['ok']==1
    assert len(feed.ws.sent)==3 and sleeps[-2:]==[10,20]
    feed.ws=Socket(['InvalidSymbol'])
    with pytest.raises(RuntimeError,match='InvalidSymbol'):feed.request({'ticks_history':'bad'})
    assert len(feed.ws.sent)==1
    feed.ws=Socket(['RateLimit']*4)
    with pytest.raises(RuntimeError,match='RateLimit'):feed.request({'active_symbols':'brief'})
    assert len(feed.ws.sent)==4


@pytest.mark.parametrize("empty_frame",[False,True])
def test_closed_connection_reopens_and_retries_same_history_request(monkeypatch,empty_frame):
    monkeypatch.setattr(deriv.time,'sleep',lambda _:None)
    sent=[]
    class Broken:
        def send(self,text):
            if not empty_frame:raise ConnectionError('closed')
        def recv(self):return ''
        def close(self):pass
    class Reopened:
        def send(self,text):sent.append(json.loads(text))
        def recv(self):return json.dumps({'req_id':sent[-1]['req_id'],'candles':[]})
        def close(self):pass
    f=deriv.Feed(socket_factory=lambda *a,**kw:Reopened());f.ws=Broken()
    payload={'ticks_history':'R_75','start':100,'end':'200','count':1}
    assert f.request(payload)=={'req_id':2,'candles':[]}
    assert {k:v for k,v in sent[0].items() if k!='req_id'}==payload
