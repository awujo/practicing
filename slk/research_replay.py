"""Bounded as-of event research. Offline; no live settings, trading or messaging writes."""
import argparse
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import sqlite3
import time

import numpy as np
import pandas as pd

from . import live
from .research import atomic_json, digest, encoded, read_input, utc, MAX_OUTPUT
from .story import DEFAULT
from .candles import _key, nominal_end

POLICIES = ('keep', 'retire_at_target', 'close_margin_0p5_range', 'fresh_story', 'age_10_days')


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items() if not str(k).startswith('_')}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return live._ts(value).isoformat()
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def expected_open(t):
    n = t.tz_convert('America/New_York')
    return not (n.dayofweek == 5 or (n.dayofweek == 4 and n.hour >= 17) or (n.dayofweek == 6 and n.hour < 17))


def gaps(frame, start, end):
    actual = set(frame.index)
    return [t for t in pd.date_range(start.ceil('h'), end, freq='h', inclusive='left')
            if expected_open(t) and t not in actual]


def close_time(t, tf):
    t = live._ts(t)
    if tf in ('D', 'W', 'M'):
        return nominal_end(t, tf)
    if tf == 'H1':
        return t + pd.Timedelta(hours=1)
    k = _key(pd.DatetimeIndex([t]), tf)[0]
    return (k + pd.Timedelta(hours=int(tf[1:])) - pd.Timedelta(hours=7)).tz_localize(
        'America/New_York', ambiguous=False).tz_convert('UTC')


def key(row):
    return f"{row['pair']}|{row['story']}|{live._ts(row['tap_time']).isoformat()}"


def extract(rows, previous, now):
    """Unfiltered study universe, not Telegram's selected standing-bias/alert population."""
    result = []
    for r in rows:
        k = key(r)
        old = previous.get(k)
        # Initial historical bootstrap is context, not a new signal available to trade now.
        if old is None:
            old = {'status': None, 'cont_breaks': r.get('cont_breaks')}
        if r.get('confirm_time') and not old.get('confirm_time') and r['status'] in ('TARGET_HIT','INVALIDATED','ENDED_FLIP','CANCELLED'):
            result.append({'kind':'CONFIRMED','story_key':k,'occurred_at':live._ts(r['confirm_time']).isoformat(),
                           'observed_at':now.isoformat(),'row':clean(r),'story_definition':clean(r.get('_story',{})),
                           'already_ended_at_observation':True})
        if r.get('_early'):
            end=close_time(r['_early']['time'],'H4')
            if end<=now:
                result.append({'kind':'EXTERNAL_BREAK_PENDING_ORIGIN','story_key':k,'occurred_at':end.isoformat(),
                               'observed_at':now.isoformat(),'row':clean(r)})
        if r['status'] != old['status']:
            when = r.get('confirm_time') if r['status'] == 'CONFIRMED' else r.get('tap_time')
            tf = 'D'
            event_time = (live._ts(when) if r['status'] == 'CONFIRMED' else close_time(when, tf)) if when is not None else now
            result.append({'kind': r['status'], 'story_key': k, 'occurred_at': event_time.isoformat(),
                           'observed_at': now.isoformat(), 'row': clean(r),
                           'story_definition': clean(r.get('_story',{})) if r['status']=='CONFIRMED' else {}})
        if r.get('line_end') and not old.get('line_end'):
            result.append({'kind':'LINE_END','story_key':k,'occurred_at':now.isoformat(),'observed_at':now.isoformat(),'row':clean(r)})
        seen = {(b['time'], b['level']) for b in live.unpack_breaks(old.get('cont_breaks'))}
        for b in live.unpack_breaks(r.get('cont_breaks')):
            end = close_time(b['time'], 'H4')
            if (b['time'], b['level']) not in seen and end <= now:
                result.append({'kind': 'CONTINUATION', 'story_key': k, 'occurred_at': end.isoformat(),
                               'observed_at': now.isoformat(), 'break_level': b['level'], 'row': clean(r)})
    # All targets/ends here use observed_at as event-time evidence: raw engine fields can be bar opens.
    for e in result:
        if e['kind'] not in ('CONFIRMED', 'TAPPED', 'CONTINUATION','EXTERNAL_BREAK_PENDING_ORIGIN'):
            e['occurred_at'] = e['observed_at']
    return result


def accepted(event, policy, state):
    r = event['row']
    if event['kind'] not in ('CONFIRMED', 'CONTINUATION') or r.get('no_trade') or r.get('line_end'):
        return False
    if r['status'] not in ('CONFIRMED', 'TARGET_HIT', 'CANCELLED'):
        return False
    after = r['status'] in ('TARGET_HIT', 'CANCELLED')
    if policy == 'keep':
        return True
    if policy == 'retire_at_target':
        return not after
    if policy == 'close_margin_0p5_range':
        return not after or event.get('break_margin_vol', 0) >= .5
    if policy == 'fresh_story':
        return not after and state.get('latest_confirmed') == event['story_key']
    if policy == 'age_10_days':
        return utc(event['observed_at']) - live._ts(r['tap_time']) <= pd.Timedelta(days=10)
    raise ValueError('unknown policy')


def outcome(event, frame, cutoff):
    when = utc(event['observed_at'])
    end = when + pd.Timedelta(hours=24)
    future = frame[(frame.index >= when) & (frame.index < end)]
    if end > cutoff or future.empty or future.index[-1] + pd.Timedelta(hours=1) != end or gaps(future, when, end):
        return {'status': 'censored', 'horizon_end': end.isoformat()}
    sign = 1 if event['row']['side'] == 'BUY' else -1
    ref, scale = event['reference_close'], event['volatility']
    signed = sign * (float(future.close.iloc[-1]) - ref) / scale
    fav = ((float(future.high.max()) - ref) if sign == 1 else (ref - float(future.low.min()))) / scale
    adverse = ((ref - float(future.low.min())) if sign == 1 else (float(future.high.max()) - ref)) / scale
    return {'status': 'observed', 'horizon_end': end.isoformat(), 'signed_move_vol': signed,
            'mfe_vol': max(0., fav), 'mae_vol': max(0., adverse)}


def connect(path):
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA max_page_count=768')  # 3 MiB database; journal fits within per-pair 10 MiB envelope.
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), identity TEXT NOT NULL, manifest TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS steps (cutoff TEXT PRIMARY KEY, state TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS progress (id INTEGER PRIMARY KEY CHECK(id=1), completed INTEGER NOT NULL);
      INSERT OR IGNORE INTO progress VALUES (1,0);
      CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS observations (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS decisions (event_id TEXT NOT NULL, policy TEXT NOT NULL, accepted INTEGER NOT NULL, PRIMARY KEY(event_id,policy));
    ''')
    return conn


def replay(frame, pair, evaluation_start, cutoff, conn, identity, manifest, seconds=600, state_fn=None, cadence="H1"):
    begun = time.monotonic()
    state_fn = state_fn or live.pair_state
    cfg = dict(DEFAULT)
    previous, memo = {}, {}
    bootstrapped = False
    with conn:
        existing = conn.execute('SELECT identity FROM meta WHERE id=1').fetchone()
        if existing and existing[0] != identity:
            raise ValueError('replay identity mismatch; choose fresh output')
        conn.execute('INSERT OR IGNORE INTO meta VALUES (1,?,?)', (identity, encoded(manifest).decode()))
    saved = conn.execute('SELECT cutoff,state FROM steps ORDER BY cutoff DESC LIMIT 1').fetchone()
    if saved:
        previous = json.loads(saved[1])
        bootstrapped = True
    ticks = frame.index + pd.Timedelta(hours=1)
    ticks = ticks[(ticks >= evaluation_start) & (ticks <= cutoff)]
    for now in ticks:
        if cadence == 'H4' and close_time(now-pd.Timedelta(hours=1), 'H4') != now:
            continue
        if saved and now <= utc(saved[0]):
            continue
        if time.monotonic() - begun >= seconds or Path(conn.execute('PRAGMA database_list').fetchone()[2]).stat().st_size > MAX_OUTPUT:
            return 'budget_exhausted'
        prefix = frame[frame.index + pd.Timedelta(hours=1) <= now]
        # Fail closed after a missing expected market hour: do not let resampling fabricate complete bars.
        if gaps(prefix, max(frame.index[0], evaluation_start-pd.Timedelta(days=1)), now):
            return 'missing_market_hours'
        rows = state_fn(pair, prefix, now, live.state_stories(['D'], cfg), cfg, memo)
        rows = [r for r in rows if r['story'] == 'D']
        events = extract(rows, previous, now) if bootstrapped else []
        confirmed = [r for r in rows if r.get('confirm_time') and not r.get('no_trade') and not r.get('line_end')
                     and r['status'] in ('CONFIRMED', 'TARGET_HIT', 'CANCELLED')]
        latest = max(confirmed, key=lambda r: live._ts(r['confirm_time'])) if confirmed else None
        context = {'latest_confirmed': key(latest) if latest else None, 'latest_side': latest['side'] if latest else None}
        vol = float((prefix.high - prefix.low).tail(24).mean())
        if not math.isfinite(vol) or vol <= 0:
            raise ValueError('insufficient positive trailing volatility')
        with conn:  # Events and progress commit together; a killed transaction is retried.
            for event in events:
                # No retrospective historical signal is an eligible forward decision.
                if utc(event['occurred_at']) != now:
                    continue
                event.update(pair=pair, reference_close=float(prefix.close.iloc[-1]), volatility=vol,
                             configuration=clean(cfg), story_age_hours=(now - live._ts(event['row']['tap_time'])).total_seconds()/3600,
                             context_quality='code-default configuration; warmup coverage recorded in manifest')
                if 'break_level' in event:
                    sign = 1 if event['row']['side'] == 'BUY' else -1
                    event['break_margin_vol'] = sign * (event['reference_close'] - event['break_level']) / vol
                eid = digest(encoded({'story': event['story_key'], 'kind': event['kind'], 'occurred': event['occurred_at'],
                                     'level': event.get('break_level')}))
                conn.execute('INSERT OR IGNORE INTO events VALUES (?,?)', (eid, encoded(event).decode()))
                for policy in POLICIES:
                    conn.execute('INSERT OR IGNORE INTO decisions VALUES (?,?,?)', (eid, policy, int(accepted(event, policy, context))))
            previous = {key(r): clean(r) for r in rows}
            bootstrapped = True
            conn.execute('DELETE FROM steps')
            conn.execute('INSERT INTO steps VALUES (?,?)', (now.isoformat(), encoded(previous).decode()))
            conn.execute('UPDATE progress SET completed=completed+1 WHERE id=1')
    return 'complete'


def report(conn, frame, cutoff):
    events = dict(conn.execute('SELECT id,payload FROM events'))
    with conn:
        for eid, payload in events.items():
            e = json.loads(payload)
            if e['kind'] in ('CONFIRMED', 'CONTINUATION'):
                conn.execute('INSERT OR REPLACE INTO observations VALUES (?,?)', (eid, encoded(outcome(e, frame, cutoff)).decode()))
    groups = {}
    for policy in POLICIES:
        choices = list(conn.execute('SELECT event_id,accepted FROM decisions WHERE policy=?', (policy,)))
        scores, unique = [], set()
        counts = Counter()
        for eid, yes in choices:
            counts['recorded_event_universe'] += 1
            counts['emitted' if yes else 'suppressed'] += 1
            if yes:
                obs = conn.execute('SELECT payload FROM observations WHERE event_id=?', (eid,)).fetchone()
                if obs:
                    o = json.loads(obs[0])
                    if o['status'] == 'observed':
                        # Multiple old stories can describe the same candle: do not inflate sample count.
                        e = json.loads(events[eid]); unit = (e['pair'], e['observed_at'], e['row']['side'])
                        if unit not in unique:
                            scores.append(o['signed_move_vol']); unique.add(unit)
                    else:
                        counts['censored'] += 1
        groups[policy] = dict(counts) | {'distinct_completed_pair_time_side': len(scores),
                         'mean_signed_move_vol': float(np.mean(scores)) if scores else None}
    return {'policies': groups, 'event_count': len(events), 'decision_steps': conn.execute('SELECT completed FROM progress WHERE id=1').fetchone()[0],
            'conclusion': 'Exploratory descriptive event comparison only. Not returns, independent samples, or a best-policy recommendation.',
            'limitations': ['History coverage may differ from live; historical gaps recorded; recent gaps fail closed', 'pair_state eligibility, not full live reconciliation',
                           'Overlapping 24h outcomes; no significance claim', 'Separate experimental entry simulator, no portfolio exposure model or untouched confirmatory holdout']}


def run_pair(path, pair, start, end, evaluation_start, out, seconds=600):
    start, end, evaluation_start = utc(start), utc(end), utc(evaluation_start)
    if not start + pd.Timedelta(days=365) <= evaluation_start < end or end-start > pd.Timedelta(days=1500) or end-evaluation_start > pd.Timedelta(days=90):
        raise ValueError('need >=365 days warmup, <=1500 total days and <=90 evaluation days')
    if not pair.isalnum() or pair.upper() != pair or len(pair) > 12 or not 1 <= seconds <= 600:
        raise ValueError('invalid pair or budget')
    frame, checksum, _ = read_input(path, start, end, max_rows=30000)
    if frame.index[0] > evaluation_start-pd.Timedelta(days=365):
        raise ValueError('actual history has less than 365 days warmup')
    code = digest(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py'))))
    manifest = {'schema': 1, 'pair': pair, 'source': 'operator-declared ctrader', 'start': start.isoformat(),
                'end': end.isoformat(), 'evaluation_start': evaluation_start.isoformat(), 'input_sha256': checksum,
                'code_sha256': code, 'python': __import__('sys').version, 'pandas': pd.__version__, 'numpy':np.__version__,
                'warmup_days': (evaluation_start-frame.index[0]).total_seconds()/86400, 'actual_first_hour': frame.index[0].isoformat(), 'actual_last_hour': frame.index[-1].isoformat(), 'warmup_rows': int((frame.index<evaluation_start).sum()), 'configuration': clean(DEFAULT), 'policies': list(POLICIES), 'decision_cadence': 'H4 closes', 'historical_gap_count': len(gaps(frame,frame.index[0],end)), 'baseline': 'pair_state event eligibility; code defaults, not DB settings'}
    root = Path(out); root.mkdir(parents=True, exist_ok=True)
    conn = connect(root / 'ledger.sqlite')
    try:
        begun=time.monotonic()
        status = replay(frame, pair, evaluation_start, end, conn, digest(encoded(manifest)), manifest, seconds, cadence='H4')
        result = report(conn, frame, end) | {'status': status, 'manifest': manifest}
        from .research_entries import evaluate
        from .research_discovery import screen
        remaining=max(0,seconds-(time.monotonic()-begun))
        result['entry_study']=evaluate(conn,frame,end,remaining) if status=='complete' else {'status':'replay_incomplete'}
        result['discovery']=screen(conn,evaluation_start,end)
        if result['entry_study']['status']=='budget_exhausted':result['status']='budget_exhausted'

        atomic_json(root / 'report.json', result, root)
        print(f'{pair}: {result["status"]}; {result["event_count"]} events; {result["decision_steps"]} decision steps', flush=True)
        return result
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'pair', 'start', 'end', 'evaluation-start', 'out'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--seconds', type=int, default=600)
    a = p.parse_args()
    result = run_pair(a.input, a.pair, a.start, a.end, a.evaluation_start, a.out, a.seconds)
    return 0 if result['status'] == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
