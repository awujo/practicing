"""Offline infrastructure pilot. No strategy scoring, database, broker or messaging access."""
import argparse
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

import pandas as pd
from .candles import _key, nominal_end, resample

MAX_INPUT, MAX_EXPANDED, MAX_OUTPUT, MAX_ROWS = 25*1024**2, 50*1024**2, 10*1024**2, 5000
FAMILIES = ('story_lifecycle age_distance freshness repeated_breaks alignment rejection confirmation entry stop '
            'target_exit context risk_abstention data_sensitivity discovery').split()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def utc(value):
    t = pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError('timestamps require explicit UTC offset')
    return t.tz_convert('UTC')


def read_input(path, start, end):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_INPUT:
        raise ValueError('input missing or exceeds 25 MiB')
    raw = path.read_bytes()
    with (gzip.GzipFile(fileobj=io.BytesIO(raw)) if path.suffix == '.gz' else io.BytesIO(raw)) as stream:
        expanded = stream.read(MAX_EXPANDED + 1)
    if len(expanded) > MAX_EXPANDED:
        raise ValueError('expanded input exceeds 50 MiB')
    frame = pd.read_csv(io.BytesIO(expanded), nrows=MAX_ROWS + 1)
    if frame.empty or len(frame) > MAX_ROWS:
        raise ValueError('input must contain 1..5000 H1 rows')
    if list(frame.columns) != ['t', 'open', 'high', 'low', 'close']:
        raise ValueError('expected t,open,high,low,close; t denotes H1 OPEN time')
    times = pd.DatetimeIndex([utc(v) for v in frame.pop('t')])
    if not times.is_monotonic_increasing or times.has_duplicates or not (times == times.floor('h')).all():
        raise ValueError('H1 open times must be unique, sorted and hour-aligned')
    for col in frame:
        frame[col] = pd.to_numeric(frame[col], errors='raise')
        if not frame[col].map(lambda x: math.isfinite(x) and x > 0).all():
            raise ValueError('OHLC must be positive and finite')
    if ((frame.high < frame[['open', 'close', 'low']].max(axis=1)) |
            (frame.low > frame[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError('inconsistent OHLC bounds')
    frame.index = times
    selected = frame[(times >= start) & (times + pd.Timedelta(hours=1) <= end)]
    if selected.empty:
        raise ValueError('no completed H1 candles in window')
    return selected, digest(raw), len(raw)


def diagnostic(frame, tf, cutoff):
    bins = resample(frame, tf)
    counts = frame.groupby(_key(frame.index, tf)).size().to_list()
    complete, incomplete, forming = [], 0, 0
    for row, count in zip(bins.to_dict('records'), counts):
        key = _key(pd.DatetimeIndex([row['start']]), tf)[0]
        start = (key - pd.Timedelta(hours=7)).tz_localize('America/New_York', ambiguous=True).tz_convert('UTC')
        end = ((key + pd.Timedelta(hours=4) - pd.Timedelta(hours=7)).tz_localize(
            'America/New_York', ambiguous=False).tz_convert('UTC') if tf == 'H4' else nominal_end(row['start'], tf))
        if end > cutoff:
            forming += 1
        elif row['start'] != start or count != int((end - start).total_seconds() // 3600):
            incomplete += 1
        else:
            complete.append({'open_time': start.isoformat(), 'close_time': end.isoformat(), 'close': float(row['close'])})
    return {'timeframe': tf, 'complete_bins': len(complete), 'incomplete_bins_excluded': incomplete,
            'forming_bins_excluded': forming, 'last_complete': complete[-1] if complete else None,
            'interpretation': 'Data diagnostic only. No breakout, policy or financial conclusion.'}


def atomic_json(path, value, root):
    data = encoded(value)
    used = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    if used + len(data) > MAX_OUTPUT:
        raise ValueError('output exceeds 10 MiB')
    tmp = path.with_suffix('.tmp')
    with tmp.open('wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def run(path, pair, source, start, end, out, seconds=600):
    begun = time.monotonic()
    if not re.fullmatch(r'[A-Z0-9]{3,12}', pair) or source != 'ctrader':
        raise ValueError('pilot requires symbol and declared ctrader source')
    if not 1 <= seconds <= 600:
        raise ValueError('runtime budget must be 1..600 seconds')
    start, end = utc(start), utc(end)
    if not pd.Timedelta(0) < end - start <= pd.Timedelta(days=90):
        raise ValueError('window must be positive and <=90 days')
    frame, input_hash, size = read_input(path, start, end)
    code_hash = digest(Path(__file__).read_bytes() + Path(__file__).with_name('candles.py').read_bytes())
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL, timeout=5).decode().strip()
    except (OSError, subprocess.SubprocessError):
        revision = 'unavailable'
    manifest = {'git_sha': revision, 'schema': 1, 'phase': 'infrastructure_only', 'pair': pair, 'source': source,
                'source_evidence': 'operator declaration, not independently authenticated',
                'availability': 'historical simulated; actual arrival time unknown',
                'start': start.isoformat(), 'cutoff': end.isoformat(), 'input_sha256': input_hash,
                'code_sha256': code_hash, 'input_bytes': size, 'rows': len(frame),
                'python': __import__('sys').version, 'pandas': pd.__version__,
                'studies': ['H4', 'D', 'W'], 'policy_candidates_evaluated': 0}
    identity = digest(encoded(manifest))
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / '.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        checkpoint = root / 'checkpoint.json'
        state = {'identity': identity, 'completed': {}}
        if checkpoint.exists():
            if checkpoint.stat().st_size > MAX_OUTPUT:
                raise ValueError('oversized checkpoint')
            state = json.loads(checkpoint.read_text())
            if state.get('identity') != identity:
                raise ValueError('resume identity mismatch; use new output directory')
            for tf, checksum in state['completed'].items():
                if (tf not in manifest['studies'] or (root / f'{tf}.json').stat().st_size > MAX_OUTPUT
                        or digest((root / f'{tf}.json').read_bytes()) != checksum):
                    raise ValueError('result checksum mismatch')
        atomic_json(root / 'manifest.json', manifest, root)
        atomic_json(root / 'catalog.json', {f: {'status': 'planned', 'specification': 'research/DESIGN.md'} for f in FAMILIES}, root)
        atomic_json(root / 'summary.json', {'status': 'running', 'conclusion': 'Infrastructure only; no financial evaluation.'}, root)
        for tf in manifest['studies']:
            if tf in state['completed']:
                continue
            if time.monotonic() - begun >= seconds:
                break
            target = root / f'{tf}.json'
            atomic_json(target, diagnostic(frame, tf, end), root)
            state['completed'][tf] = digest(target.read_bytes())
            atomic_json(checkpoint, state, root)
        status = 'complete' if len(state['completed']) == 3 else 'budget_exhausted'
        total_bins = sum(json.loads((root / f'{tf}.json').read_text())['complete_bins'] for tf in state['completed'])
        atomic_json(root / 'summary.json', {'status': status, 'data_adequacy': 'diagnostic_bins_available' if total_bins else 'insufficient_complete_bins',
                    'strategy_evidence': 'insufficient: strategy studies not implemented', 'completed': sorted(state['completed']),
                    'wall_seconds': round(time.monotonic() - begun, 3),
                    'conclusion': 'No strategy comparison or profitability claim. Replay gate not implemented.'}, root)
        return status
    except Exception as exc:
        try:
            atomic_json(root / 'summary.json', {'status': 'failed', 'error_type': type(exc).__name__,
                        'error': str(exc), 'conclusion': 'No research conclusion.'}, root)
        except (OSError, ValueError):
            pass  # A full/unwritable output cannot promise a failure artifact. Workflow also captures logs.
        raise
    finally:
        lock.unlink()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['input', 'pair', 'source', 'start', 'end']:
        p.add_argument('--' + name, required=True)
    p.add_argument('--out', default='research-output')
    p.add_argument('--seconds', type=int, default=600)
    a = p.parse_args()
    try:
        status = run(a.input, a.pair, a.source, a.start, a.end, a.out, a.seconds)
        print(f'Research infrastructure: {status}. No strategy performance evaluation.')
        return 0 if status == 'complete' else 2
    except (ValueError, OSError, KeyError) as exc:
        print(f'Research rejected: {type(exc).__name__}: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
