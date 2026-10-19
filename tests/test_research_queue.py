import json
import sys
from types import SimpleNamespace
from slk import research_queue as queue


def test_only_explicit_completion_counts():
    assert queue.pending_pairs(['A', 'B', 'C'], [
        {'pair': 'A', 'status': 'complete'}, {'pair': 'B', 'status': 'failed'},
        {'pair': 'OTHER', 'status': 'complete'}]) == ['B', 'C']


def exercise(monkeypatch, tmp_path, success):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
    monkeypatch.setenv('GITHUB_RUN_ID', 'queue123')
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(tmp_path / 'summary'))
    monkeypatch.setitem(sys.modules, 'slk.backtest', SimpleNamespace(PAIRS=list('ABCDE')))
    dispatched = []
    current = {}

    def gh(*args):
        if args[:2] == ('workflow', 'run'):
            fields = [a for a in args if a.startswith(('pairs=', 'queue_token='))]
            current.update(dict(a.split('=', 1) for a in fields))
            dispatched.append(current['pairs'])
            return ''
        if args[:2] == ('run', 'list'):
            return json.dumps([{'databaseId': len(dispatched),
                'displayTitle': 'Research batch ' + current['queue_token']}])
        if args[:2] == ('run', 'view'):
            return json.dumps({'status': 'completed', 'conclusion': 'success' if success else 'failure'})
        if args[:2] == ('run', 'download'):
            directory = args[args.index('--dir') + 1]
            pairs = list('ABCD') if args[2] == 'existing' else current['pairs'].split(',')
            from pathlib import Path
            Path(directory, 'batch-report.json').write_text(json.dumps({'results': [
                {'pair': p, 'status': 'complete' if success else 'failed'} for p in pairs]}))
            return ''
        raise AssertionError(args)

    monkeypatch.setattr(queue, 'gh', gh)
    return dispatched


def test_adopts_existing_and_starts_only_remaining(monkeypatch, tmp_path):
    dispatched = exercise(monkeypatch, tmp_path, True)
    queue.main('existing')
    assert dispatched == ['E']
    assert json.loads((tmp_path / 'research-queue.json').read_text())['unfinished'] == []


def test_failed_pairs_stop_after_two_attempts(monkeypatch, tmp_path):
    import pytest
    dispatched = exercise(monkeypatch, tmp_path, False)
    with pytest.raises(SystemExit):
        queue.main()
    assert dispatched == ['A,B,C,D', 'A,B,C,D', 'E', 'E']
    assert set(json.loads((tmp_path / 'research-queue.json').read_text())['attempts'].values()) == {2}
