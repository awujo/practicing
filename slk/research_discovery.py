"""Predeclared shallow screening; selects on development data only. No ANN or significance claim."""
import json
import pandas as pd
from .research import encoded
from .research_replay import utc

GROUPS=('all','age_under_10_days','origin_structure_agrees','close_margin_0p5_range')


def member(name,event):
    if name=='all':return True
    if name=='age_under_10_days':return event['story_age_hours']<=240
    if name=='origin_structure_agrees':return event['row'].get('trend')==('up' if event['row']['side']=='BUY' else 'down')
    if name=='close_margin_0p5_range':return event.get('break_margin_vol',0)>=.5
    raise ValueError('unknown group')


def screen(conn,start,end):
    split=start+(end-start)/2
    train,test=[],[];seen=set()
    records=list(conn.execute('SELECT e.id,e.payload,o.payload FROM events e JOIN observations o ON e.id=o.event_id'))
    # Canonical sample = latest confirmed story, then latest tap, then stable event identity.
    records.sort(key=lambda x:(json.loads(x[1])['pair'],json.loads(x[1])['observed_at'],json.loads(x[1])['row']['side'],
        -utc(json.loads(x[1])['row'].get('confirm_time') or json.loads(x[1])['observed_at']).value,
        -utc(json.loads(x[1])['row'].get('tap_time') or json.loads(x[1])['observed_at']).value,x[0]))
    for eid,payload,observed in records:
        e,o=json.loads(payload),json.loads(observed)
        accepted=conn.execute("SELECT accepted FROM decisions WHERE event_id=? AND policy='keep'",(eid,)).fetchone()
        if not accepted or not accepted[0] or o['status']!='observed':continue
        unit=(e['pair'],e['observed_at'],e['row']['side'])
        if unit in seen:continue
        seen.add(unit)
        if utc(o['horizon_end'])<=split:train.append((e,o))
        elif utc(e['observed_at'])>=split:test.append((e,o))
    def stats(data,group):
        values=[o['signed_move_vol'] for e,o in data if member(group,e)]
        return {'distinct_pair_time_side':len(values),'mean_signed_move_vol':sum(values)/len(values) if values else None}
    development={g:stats(train,g) for g in GROUPS}
    eligible=[g for g in GROUPS if development[g]['distinct_pair_time_side']>=30]
    selected=max(eligible,key=lambda g:development[g]['mean_signed_move_vol']) if eligible else None
    # Only the preselected group is evaluated on the later period; never select by test outcomes.
    validation=stats(test,selected) if selected else None
    result={'status':'exploratory_only' if validation and validation['distinct_pair_time_side']>=30 else 'insufficient_data',
            'split':split.isoformat(),'purge':'24-hour outcomes crossing split excluded',
            'development':development,'selected_on_development':selected,'later_period':validation,
            'decision_steps':conn.execute('SELECT completed FROM progress').fetchone()[0], 'canonical_sample':'latest confirmation, latest tap, stable event id per pair/time/side', 'attempted_groups':list(GROUPS),'minimum_count_per_period':30,
            'warning':'Counts do not establish independence or statistical power. One exploratory split, not untouched confirmatory evidence. No automatic rule changes.'}
    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS discovery_findings (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT)')
        conn.execute('INSERT OR REPLACE INTO discovery_findings VALUES (1,?)',(encoded(result).decode(),))
    return result
