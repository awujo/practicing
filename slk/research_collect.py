"""Explicit bounded IC Markets research exports; no fallback and no trading calls."""
import argparse
import json
from pathlib import Path
import re
import time

import pandas as pd
from .backtest import PAIRS
from .research import atomic_json


def select(pairs, offset=0, limit=4):
    names = PAIRS if not pairs.strip() else [s.strip().upper() for s in pairs.split(',')]
    if not names or len(names) > 40 or len(set(names)) != len(names) or any(not re.fullmatch('[A-Z0-9]{3,12}', p) for p in names):
        raise ValueError('choose 1..40 distinct symbols')
    if not 0 <= offset < len(names) or not 1 <= limit <= 4:
        raise ValueError('offset out of range or batch limit outside 1..4')
    return names, names[offset:offset+limit]


def collect(pairs, offset, limit, root, days=1200, evaluation_days=21):
    if not 365 <= days <= 1500 or not 1 <= evaluation_days <= 90 or days-evaluation_days < 365:
        raise ValueError('history 365..1500 days, evaluation 1..90 days, >=365 days warmup')
    all_pairs, selected = select(pairs, offset, limit)
    out = Path(root); out.mkdir(parents=True, exist_ok=True)
    cutoff = pd.Timestamp.now(tz='UTC').floor('h')
    start = cutoff-pd.Timedelta(days=days)
    entries = []; begun = time.monotonic()
    # Same underlying authenticated client as the live feed, but never source-switch or call update/backfill.
    from . import store
    try:
        feed = store.get_feed()
        feed.prefetch(selected)
        for pair in selected:
            if time.monotonic()-begun > 480:
                entries.append({'pair': pair, 'status': 'budget_exhausted'}); continue
            try:
                rows = feed.bars(pair, int(start.timestamp()), int(cutoff.timestamp()))
                f = pd.DataFrame([r[:5] for r in rows], columns=['t','open','high','low','close'])
                f['t'] = pd.to_datetime(f['t'], unit='s', utc=True)
                f = f[(f.t >= start) & (f.t+pd.Timedelta(hours=1) <= cutoff)].sort_values('t').drop_duplicates('t')
                if len(f) > 30000 or f.empty:
                    raise ValueError('no candles or export exceeds 30000 H1 rows')
                name=pair+'_H1_ctrader.csv.gz'
                f.to_csv(out/name,index=False)
                entries.append({'pair':pair,'status':'ready','file':name,'rows':len(f)})
            except Exception as exc:
                # Broker errors can contain credentials; persist only the type, never raw exception text.
                entries.append({'pair':pair,'status':'acquisition_failed','error_type':type(exc).__name__})
    finally:
        store.close_feed()
    manifest={'source':'ctrader','start':start.isoformat(),'end':cutoff.isoformat(),
              'evaluation_start':(cutoff-pd.Timedelta(days=evaluation_days)).isoformat(),
              'requested_pairs':all_pairs,'selected_pairs':selected,'offset':offset,
              'next_offset':offset+len(selected) if offset+len(selected)<len(all_pairs) else None,'entries':entries}
    atomic_json(out/'batch.json',manifest,out)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pairs',default='');p.add_argument('--offset',type=int,default=0);p.add_argument('--limit',type=int,default=4)
    p.add_argument('--out',default='research-input');p.add_argument('--days',type=int,default=1200)
    a=p.parse_args()
    try: result=collect(a.pairs,a.offset,a.limit,a.out,a.days)
    except Exception as exc: raise SystemExit(f'Acquisition failed: {type(exc).__name__}')
    print(json.dumps(result,indent=2));return 0 if all(e['status']=='ready' for e in result['entries']) else 2


if __name__=='__main__':raise SystemExit(main())
