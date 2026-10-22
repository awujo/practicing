from datetime import datetime,timezone,timedelta
import pytest
from slk import news,settings
UTC=timezone.utc
NOW=datetime(2026,10,22,12,30,tzinfo=UTC)


def event(date='2026-10-22T09:30:00-04:00',**kw):
    return dict(title='CPI',country='USD',date=date,impact='High',forecast='2.0%',previous='1.8%',**kw)


def test_feed_utc_dedup_and_invalid_dates():
    events=news.normalize([event(),event(),event(date='not-a-date'),event(date='2026-10-22T12:00:00')])
    assert len(events)==1 and events[0]['time']=='2026-10-22T13:30:00+00:00'
    assert news.normalize([event(date='2026-12-22T08:30:00-05:00')])[0]['time']=='2026-12-22T13:30:00+00:00'


def test_reminder_window_preferences_and_past_events():
    events=news.normalize([event()]); vals=settings.load({'news_daily':'off'})
    assert len(news.plans(events,vals,NOW))==1
    assert '60 minutes' in news.plans(events,vals,NOW)[0][1]
    assert not news.plans(events,vals,NOW-timedelta(seconds=1))
    assert not news.plans(events,vals,NOW+timedelta(minutes=6))
    assert not news.plans(events,vals,NOW+timedelta(hours=1))
    assert not news.plans(events,settings.load({'news_enabled':'off'}),NOW)
    assert not news.plans(events,settings.load({'news_currencies':'GBP'}),NOW)
    assert not news.plans(events,settings.load({'news_impact':'low'}),NOW)


def test_daily_local_date_and_key():
    now=datetime(2026,10,22,6,5,tzinfo=UTC) #07:05 WAT
    plans=news.plans(news.normalize([event()]),settings.load(),now)
    assert len(plans)==1 and plans[0][0]=='daily:2026-10-22'
    assert '14:30' in plans[0][1]
    assert not news.plans([],settings.load(),now+timedelta(hours=1))


def test_cache_fetch_failure_uses_marked_cache():
    class DB:
        def query(self,*a):return [{'payload':'[]','fetched_at':int(NOW.timestamp())-3600}]
        def execute(self,*a):pytest.fail('failed fetch should not overwrite cache')
    def fail():raise RuntimeError('offline')
    result=news.calendar(DB(),NOW,fail)
    assert result['stale'] and result['events']==[]


def test_delivery_recipient_and_dedup():
    class Cursor:
        def __init__(self):self.wins=[1,0]
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def execute(self,*a):return self.wins.pop(0)
    class DB:
        def __init__(self):self.c=Cursor();self.writes=[]
        def _c(self):return self
        def cursor(self):return self.c
        def execute(self,*a):self.writes.append(a)
    db=DB();sent=[]
    sender=lambda text,chat:sent.append((chat,text)) or True
    assert news.deliver(db,42,'x','hello',sender,NOW)
    assert not news.deliver(db,42,'x','hello',sender,NOW)
    assert sent==[(42,'hello')]
    assert any('sent_at=%s' in sql for sql,args in db.writes)


def test_cache_does_not_claim_old_week_covers_today():
    import json
    old=news.normalize([event(date='2026-10-12T09:00:00-04:00')])
    class DB:
        def query(self,*a):return [{'payload':json.dumps(old),'fetched_at':int(NOW.timestamp())}]
    assert not news.calendar(DB(),NOW)['covered']
