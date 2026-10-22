"""Scheduled economic-calendar events, cached once and filtered per Telegram user. No AI calls."""
import hashlib
import json
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

FEED = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
UTC = timezone.utc


def normalize(raw):
    events=[]
    for r in raw:
        try:
            at=datetime.fromisoformat(r['date'])
            if at.tzinfo is None: continue
            title=str(r['title']).strip()[:250]
            currency=str(r['country']).upper()
            impact=str(r['impact']).lower()
            if not title or currency not in {'USD','EUR','GBP','JPY','AUD','NZD','CAD','CHF','CNY','ALL'}: continue
            if impact not in {'high','medium','low','holiday'}: continue
            at=at.astimezone(UTC)
            identity=hashlib.sha256(json.dumps([title,currency,at.isoformat()]).encode()).hexdigest()
            events.append(dict(id=identity,title=title,currency=currency,impact=impact,
                               time=at.isoformat(),forecast=str(r.get('forecast') or '')[:100],
                               previous=str(r.get('previous') or '')[:100]))
        except (ValueError,KeyError,TypeError): continue
    return sorted({e['id']:e for e in events}.values(), key=lambda e:(e['time'],e['currency'],e['title']))


def fetch():
    url=os.environ.get('NEWS_CALENDAR_URL') or FEED
    if not url.startswith('https://'): raise ValueError('calendar feed requires HTTPS')
    req=urllib.request.Request(url,headers={'User-Agent':'SLK-economic-calendar/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r:
        body=r.read(2*1024*1024+1)
    if len(body)>2*1024*1024: raise ValueError('calendar feed too large')
    raw=json.loads(body)
    if not isinstance(raw,list) or len(raw)>3000: raise ValueError('unexpected calendar feed')
    events=normalize(raw)
    if raw and not events: raise ValueError('calendar feed contains no recognized events')
    return events


def calendar(db,now=None,loader=fetch):
    now=now or datetime.now(UTC)
    stamp=int(now.timestamp())
    rows=db.query('SELECT payload,fetched_at FROM news_cache WHERE id=1')
    cached=rows[0] if rows else None
    error=False
    if not cached or stamp-int(cached['fetched_at'])>=1800:
        try:
            events=loader()
            db.execute('INSERT INTO news_cache (id,payload,fetched_at) VALUES (1,%s,%s) '
                       'ON DUPLICATE KEY UPDATE payload=VALUES(payload),fetched_at=VALUES(fetched_at)',
                       (json.dumps(events),stamp))
            cached={'payload':json.dumps(events),'fetched_at':stamp}
        except Exception:
            error=True
            if not cached: raise RuntimeError('Calendar temporarily unavailable') from None
    events=json.loads(cached['payload'])
    day=now.astimezone(ZoneInfo('America/New_York')).date()
    starts=[]
    for event in events:
        date=datetime.fromisoformat(event['time']).astimezone(ZoneInfo('America/New_York')).date()
        starts.append(date-timedelta(days=(date.weekday()+1)%7))
    covered=any(start<=day<start+timedelta(days=7) for start in starts)
    return dict(events=events,covered=covered,fetched_at=int(cached['fetched_at']),
                stale=error or stamp-int(cached['fetched_at'])>=1800,
                source=os.environ.get('NEWS_CALENDAR_SOURCE') or 'Forex Factory',
                source_url=os.environ.get('NEWS_CALENDAR_SOURCE_URL') or 'https://www.forexfactory.com/calendar')


def selected(events,vals):
    return [e for e in events if e['currency'] in vals['news_currencies'] and e['impact'] in vals['news_impact']]


def plans(events,vals,now):
    """Due reminders: within five minutes of the 60-minute mark, never after release.
    Daily summary is available for60min after chosen local hour; never sends overnight catch-up.
    """
    if not vals['news_enabled']: return []
    tz=ZoneInfo(vals['display_tz'])
    local=now.astimezone(tz)
    chosen=selected(events,vals)
    out=[]
    if vals['news_daily'] and local.hour==vals['news_summary_hour']:
        todays=[e for e in chosen if datetime.fromisoformat(e['time']).astimezone(tz).date()==local.date()]
        lines=[f"🗓 Economic calendar · {local:%a %d %b}", f"Times: {vals['display_tz']}"]
        lines += [f"{datetime.fromisoformat(e['time']).astimezone(tz):%H:%M} · {e['currency']} · {e['impact'].upper()} · {e['title']}" for e in todays]
        if not todays: lines.append('No matching events scheduled today in the available calendar.')
        lines.append('Scheduled times can change. Source: '+(os.environ.get('NEWS_CALENDAR_SOURCE') or 'Forex Factory'))
        # One bounded message avoids duplicate partial multipart daily deliveries.
        text='\n'.join(lines)
        if len(text)>3800: text=text[:3700]+'\nMore events in Mini App → News.'
        out.append(('daily:'+local.date().isoformat(),text))
    if vals['news_reminders']:
        for e in chosen:
            at=datetime.fromisoformat(e['time'])
            minutes=(at-now).total_seconds()/60
            if 55<=minutes<=60:
                out.append(('reminder:'+e['id'],
                    f"⏰ News in about {round(minutes)} minutes\n{e['currency']} · {e['impact'].upper()} · {e['title']}\n"
                    f"{at.astimezone(tz):%a %d %b %H:%M} · {vals['display_tz']}\n"
                    f"Forecast: {e['forecast'] or '—'} · Previous: {e['previous'] or '—'}\n"
                    'Scheduled time may change. Source: '+(os.environ.get('NEWS_CALENDAR_SOURCE') or 'Forex Factory')))
    return out


def deliver(db,uid,key,text,sender,now):
    """Atomic ten-minute lease; failed delivery can retry, successful message is deduplicated."""
    stamp=int(now.timestamp())
    db.execute('INSERT IGNORE INTO news_deliveries (user_id,event_key,claimed_at,created_at) VALUES (%s,%s,0,%s)',(uid,key,stamp))
    # slk.db.execute returns lastrowid, so query the affected-row count on the same connection.
    with db._c().cursor() as c:
        won=c.execute('UPDATE news_deliveries SET claimed_at=%s WHERE user_id=%s AND event_key=%s '
                      'AND sent_at IS NULL AND claimed_at < %s',(stamp,uid,key,stamp-600))
    if not won: return None
    try:
        ok=sender(text,chat=uid)
    except Exception:
        ok=False
    if ok:
        db.execute('UPDATE news_deliveries SET sent_at=%s WHERE user_id=%s AND event_key=%s AND claimed_at=%s',(stamp,uid,key,stamp))
    else:
        db.execute('UPDATE news_deliveries SET claimed_at=0 WHERE user_id=%s AND event_key=%s AND sent_at IS NULL AND claimed_at=%s',(uid,key,stamp))
    return bool(ok)


def send(text,chat):
    """No strategy/pandas import in the lightweight calendar service."""
    token=os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token: return False
    request=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',
        data=json.dumps({'chat_id':chat,'text':text,'disable_web_page_preview':True}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=20) as response:
            return bool(json.load(response).get('ok'))
    except Exception: return False


def tick():
    from . import db,settings,tenancy
    now=datetime.now(UTC)
    cache=calendar(db,now)
    if not cache['covered']: return {'ok':True,'sent':0,'note':'Current calendar week not available'}
    if now.timestamp()-cache['fetched_at']>6*3600: raise RuntimeError('Calendar cache too old to send alerts')
    users={tenancy.owner_id(),*(int(r['user_id']) for r in db.query('SELECT user_id FROM app_users'))}
    cursor=int(db.get_setting('news_user_cursor','0') or '0')
    ordered=sorted(u for u in users if u>cursor)+sorted(u for u in users if u<=cursor)
    sent=failed=skipped=processed=0
    deadline=time.monotonic()+80
    for uid in ordered:
        if time.monotonic()>=deadline: break
        with tenancy.scope(uid): vals=settings.load(db.get_settings())
        for key,text in plans(cache['events'],vals,datetime.now(UTC)):
            if time.monotonic()>=deadline: break
            current=datetime.now(UTC)
            fresh=dict(plans(cache['events'],vals,current))
            if key not in fresh: continue
            result=deliver(db,uid,key,fresh[key],send,current)
            if result is True: sent+=1
            elif result is False: failed+=1
            else: skipped+=1
        processed+=1
        db.set_setting('news_user_cursor',str(uid))
    db.execute('DELETE FROM news_deliveries WHERE created_at < %s',
               (int(now.timestamp())-30*86400,))
    return {'ok':True,'users':len(users),'processed':processed,'deferred':len(users)-processed,'sent':sent,'failed':failed,'deduplicated':skipped,'fetched_at':cache['fetched_at']}


if __name__=='__main__':
    from . import db
    db.apply_schema()
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--refresh-only',action='store_true')
    args=parser.parse_args()
    if args.refresh_only:
        result=calendar(db)
        print(json.dumps({'ok':True,'events':len(result['events']),'covered':result['covered'],'stale':result['stale']}))
    else: print(json.dumps(tick()))
