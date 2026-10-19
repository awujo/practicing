"""Offline infrastructure checks; these do not assert strategy profitability."""
import json
from pathlib import Path

import pandas as pd
import pytest

from slk import research as r


def frame(start='2026-10-19T01:00:00Z', n=9):
    idx = pd.date_range(start, periods=n, freq='h')
    return pd.DataFrame({'t': idx.astype(str), 'open': 1., 'high': 1.2, 'low': .8, 'close': 1.1})


def fixture(tmp_path, data=None):
    p = tmp_path / 'EURUSD_H1_ctrader.csv.gz'
    (frame() if data is None else data).to_csv(p, index=False)
    return p


def run(tmp_path, path, **kw):
    args = dict(path=path, pair='EURUSD', source='ctrader', start='2026-10-19T01:00Z',
                end='2026-10-19T10:00Z', out=tmp_path / 'out')
    return r.run(**(args | kw))


def test_complete_resume_and_tamper(tmp_path):
    p = fixture(tmp_path)
    assert run(tmp_path, p) == 'complete'
    out = tmp_path / 'out'
    before = (out / 'H4.json').read_bytes()
    assert run(tmp_path, p) == 'complete'
    assert (out / 'H4.json').read_bytes() == before
    assert json.loads((out / 'manifest.json').read_text())['policy_candidates_evaluated'] == 0
    (out / 'H4.json').write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        run(tmp_path, p)
    assert not (out / '.lock').exists()


def test_identity_change_rejected(tmp_path):
    p = fixture(tmp_path)
    run(tmp_path, p)
    with pytest.raises(ValueError, match='identity'):
        run(tmp_path, p, end='2026-10-19T09:00Z')


@pytest.mark.parametrize('change', ['nan', 'ohlc', 'duplicate', 'order', 'timezone', 'hour'])
def test_bad_data(tmp_path, change):
    f = frame()
    if change == 'nan': f.loc[0, 'close'] = float('nan')
    if change == 'ohlc': f.loc[0, 'close'] = 2.
    if change == 'duplicate': f.loc[1, 't'] = f.loc[0, 't']
    if change == 'order': f = f.iloc[::-1]
    if change == 'timezone': f.loc[0, 't'] = '2026-10-19 01:00:00'
    if change == 'hour': f.loc[0, 't'] = '2026-10-19T01:30:00Z'
    with pytest.raises(ValueError):
        run(tmp_path, fixture(tmp_path, f))


def test_bounds(tmp_path, monkeypatch):
    p = fixture(tmp_path)
    with pytest.raises(ValueError, match='90 days'):
        run(tmp_path, p, end='2027-10-19T10:00Z')
    with pytest.raises(ValueError, match='600'):
        run(tmp_path, p, seconds=601)
    monkeypatch.setattr(r, 'MAX_ROWS', 2)
    with pytest.raises(ValueError, match='5000'):
        run(tmp_path, p)


@pytest.mark.parametrize('cutoff,expected', [('2026-10-19T08:59:59Z', '2026-10-19T05:00:00+00:00'),
                                          ('2026-10-19T09:00:00Z', '2026-10-19T09:00:00+00:00')])
def test_closed_boundary(tmp_path, cutoff, expected):
    p = fixture(tmp_path)
    f, _, _ = r.read_input(p, r.utc('2026-10-19T01:00Z'), r.utc(cutoff))
    d = r.diagnostic(f, 'H4', r.utc(cutoff))
    assert d['last_complete']['close_time'] == expected


def test_missing_hour_excluded_and_future_invariant(tmp_path):
    p = fixture(tmp_path)
    cutoff = r.utc('2026-10-19T09:00Z')
    f, _, _ = r.read_input(p, r.utc('2026-10-19T01:00Z'), cutoff)
    baseline = r.diagnostic(f, 'H4', cutoff)
    # read_input excludes future rows from decisions, even if exported input contains them.
    more = frame(n=20)
    f2, _, _ = r.read_input(fixture(tmp_path, more), r.utc('2026-10-19T01:00Z'), cutoff)
    assert r.diagnostic(f2, 'H4', cutoff) == baseline
    incomplete = f.drop(f.index[-2])
    assert r.diagnostic(incomplete, 'H4', cutoff)['complete_bins'] == baseline['complete_bins'] - 1


def test_resume_partial_and_failed_write(tmp_path, monkeypatch):
    p = fixture(tmp_path)
    original = r.diagnostic
    def fail(frame, tf, cutoff):
        if tf == 'D': raise ValueError('injected failure')
        return original(frame, tf, cutoff)
    monkeypatch.setattr(r, 'diagnostic', fail)
    with pytest.raises(ValueError, match='injected'):
        run(tmp_path, p)
    state = json.loads((tmp_path / 'out' / 'checkpoint.json').read_text())
    assert list(state['completed']) == ['H4']
    monkeypatch.setattr(r, 'diagnostic', original)
    assert run(tmp_path, p) == 'complete'


def test_budget_exhausted(tmp_path, monkeypatch):
    p = fixture(tmp_path)
    ticks = iter([0., 601., 602.])
    monkeypatch.setattr(r.time, 'monotonic', lambda: next(ticks))
    assert run(tmp_path, p) == 'budget_exhausted'


def test_compressed_and_output_limits(tmp_path, monkeypatch):
    p = fixture(tmp_path)
    monkeypatch.setattr(r, 'MAX_EXPANDED', 10)
    with pytest.raises(ValueError, match='expanded'):
        run(tmp_path, p)
    monkeypatch.setattr(r, 'MAX_OUTPUT', 10)
    with pytest.raises(ValueError, match='output'):
        r.atomic_json(tmp_path / 'x.json', {'long': 'x'*30}, tmp_path)


@pytest.mark.parametrize('start,end,tf', [
    ('2026-10-18T21:00Z', '2026-10-19T21:00Z', 'D'),
    ('2026-10-18T21:00Z', '2026-10-23T21:00Z', 'W'),
    ('2026-11-01T05:00Z', '2026-11-01T10:00Z', 'H4'),
    ('2026-03-08T06:00Z', '2026-03-08T09:00Z', 'H4'),
])
def test_daily_weekly_and_dst_boundary(tmp_path, start, end, tf):
    begin, close = r.utc(start), r.utc(end)
    n = int((close - begin).total_seconds() // 3600)
    p = fixture(tmp_path, frame(start, n))
    f, _, _ = r.read_input(p, begin, close)
    assert r.diagnostic(f, tf, close)['last_complete']['close_time'] == close.isoformat()
    early = close - pd.Timedelta(seconds=1)
    f, _, _ = r.read_input(p, begin, early)
    assert r.diagnostic(f, tf, early)['last_complete'] is None


def test_insufficient_bins_explicit(tmp_path):
    p = fixture(tmp_path, frame(n=1))
    run(tmp_path, p)
    summary = json.loads((tmp_path / 'out' / 'summary.json').read_text())
    assert summary['data_adequacy'] == 'insufficient_complete_bins'
    assert summary['strategy_evidence'].startswith('insufficient')


def test_failed_resume_replaces_old_success(tmp_path):
    p = fixture(tmp_path)
    run(tmp_path, p)
    with pytest.raises(ValueError):
        run(tmp_path, p, pair='GBPUSD')
    assert json.loads((tmp_path / 'out' / 'summary.json').read_text())['status'] == 'failed'


def test_lock_prevents_concurrent_takeover(tmp_path):
    p = fixture(tmp_path)
    out = tmp_path / 'out'
    out.mkdir()
    (out / '.lock').write_text('')
    with pytest.raises(FileExistsError):
        run(tmp_path, p)
    assert (out / '.lock').exists()
