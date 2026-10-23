"""Explicit calendar aggregation of frozen complete base bars."""
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd
from .types import Bar, utc


def minutes(tf):
    if tf.startswith('H') and tf[1:].isdigit(): return int(tf[1:])*60
    if tf.startswith('M') and tf != 'M' and tf[1:].isdigit(): return int(tf[1:])
    if tf not in ('D','W','M','MN1'): raise ValueError('unsupported timeframe '+tf)
    return None


def bounds(at, tf, anchor):
    at=pd.Timestamp(utc(at))
    if anchor == 'ny17_wall_v2':
        shifted=at.tz_convert('America/New_York').tz_localize(None)+pd.Timedelta(hours=7)
    elif anchor == 'utc_epoch_v1': shifted=at.tz_convert('UTC').tz_localize(None)
    else: raise ValueError('unsupported explicit anchor '+anchor)
    n=minutes(tf)
    if n:
        first=(pd.Timestamp('1970-01-01')+pd.Timedelta(minutes=int(shifted.value//(60*10**9))//n*n)) if anchor=='utc_epoch_v1' else shifted.floor('D')+pd.Timedelta(minutes=(shifted.hour*60+shifted.minute)//n*n)
        last=first+pd.Timedelta(minutes=n)
    elif tf=='D': first=shifted.floor('D'); last=first+pd.Timedelta(days=1)
    elif tf=='W':
        first=shifted.floor('D')-pd.Timedelta(days=shifted.dayofweek)
        last=first+pd.Timedelta(days=5 if anchor=='ny17_wall_v2' else 7)
    else: first=shifted.to_period('M').to_timestamp(); last=first+pd.offsets.MonthBegin(1)
    def convert(x):
        if anchor=='ny17_wall_v2': return (x-pd.Timedelta(hours=7)).tz_localize('America/New_York',ambiguous=True,nonexistent='shift_forward').tz_convert('UTC').to_pydatetime()
        return x.tz_localize('UTC').to_pydatetime()
    return convert(first),convert(last)


def is_open(at, calendar):
    if isinstance(calendar,str): calendar={'id':calendar}
    cid=calendar['id']; at=utc(at)
    if cid=='24x7_utc_v1': opened=True
    elif cid=='fx_ny_v1':
        n=at.astimezone(ZoneInfo('America/New_York'))
        opened=not ((n.weekday()==4 and n.hour>=17) or n.weekday()==5 or (n.weekday()==6 and n.hour<17))
    elif cid=='explicit_intervals_v1': opened=any(utc(a)<=at<utc(b) for a,b in calendar.get('open_intervals',()))
    else: raise ValueError('unsupported calendar '+cid)
    if any(utc(a)<=at<utc(b) for a,b in calendar.get('closed_intervals',())): return False
    return opened


def expected_slots(start,end,base_tf,calendar):
    step=timedelta(minutes=minutes(base_tf) or 0)
    if step.total_seconds()<=0: raise ValueError('base duration must be intraday')
    at=utc(start); end=utc(end)
    while at<end:
        if is_open(at,calendar): yield at
        at+=step


def aggregate(bars, tf, instrument=None, as_of=None, calendar=None, anchor=None):
    """Return {'bars': tuple, 'coverage': diagnostics}; never upsample."""
    bars=tuple(bars)
    if not bars: return {'bars':(), 'coverage':{'status':'EMPTY','incomplete':[]}}
    base=minutes(bars[0].tf); target=minutes(tf)
    if base is None or (target is not None and (target<base or target%base)):
        raise ValueError('UNRESOLVED_RESOLUTION: '+bars[0].tf+' cannot build '+tf)
    calendar=calendar or (instrument.calendar_id if instrument else None)
    anchor=anchor or (instrument.anchor_id if instrument else None)
    if calendar is None or anchor is None: raise ValueError('explicit calendar and anchor required')
    clock=utc(as_of) if as_of else max(b.available_at for b in bars)
    if any(a.start>=b.start or a.end>b.start for a,b in zip(bars,bars[1:])): raise ValueError('duplicate, unordered or overlapping bars')
    if any(b.instrument!=bars[0].instrument or (instrument and b.instrument!=instrument.symbol) for b in bars): raise ValueError('mixed instrument')
    if any(not is_open(b.start,calendar) for b in bars): raise ValueError('bar outside calendar')
    grouped={}
    # Enumerate expected slots, including bins with no observed rows at all.
    first_bound=bounds(bars[0].start,tf,anchor)[0]
    for slot in expected_slots(first_bound,clock,bars[0].tf,calendar):
        grouped.setdefault(bounds(slot,tf,anchor),[])
    for b in bars:
        if b.tf!=bars[0].tf: raise ValueError('mixed base timeframes')
        lo,hi=bounds(b.start,tf,anchor)
        grouped.setdefault((lo,hi),[]).append(b)
    out=[]; incomplete=[]; segment=0; gap=False
    for (lo,hi),rows in sorted(grouped.items()):
        rows=sorted(rows,key=lambda b:b.start)
        wanted=set(expected_slots(lo,hi,bars[0].tf,calendar)); present={b.start for b in rows if b.complete and b.available_at<=clock}
        missing=wanted-present
        crossing=any(b.start<lo or b.end>hi for b in rows)
        if missing or crossing or hi>clock or any(b.available_at>clock or not b.complete for b in rows):
            incomplete.append({'start':lo.isoformat(),'end':hi.isoformat(),'missing_slots':len(missing),'crossing':crossing,'forming':hi>clock}); gap=True; continue
        if not wanted: continue
        if gap: segment+=1; gap=False
        out.append(Bar(rows[0].instrument,tf,lo,hi,rows[0].open_ticks,max(b.high_ticks for b in rows),min(b.low_ticks for b in rows),rows[-1].close_ticks,max(hi,max(b.available_at for b in rows)),rows[0].source_id,str(segment)))
    return {'bars':tuple(out),'coverage':{'status':'COMPLETE' if not incomplete else 'PARTIAL','incomplete':incomplete,'complete_bars':len(out),'calendar':calendar,'anchor':anchor}}
