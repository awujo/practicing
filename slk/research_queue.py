"""Bounded Actions coordinator; no broker, trading, or AI calls."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True).strip()


def pending_pairs(pairs, results):
    """Only an explicit complete result removes a pair from the queue."""
    complete = {r['pair'] for r in results if r.get('status') == 'complete'}
    return [p for p in pairs if p not in complete]


def main(existing=''):
    from .backtest import PAIRS
    pairs = PAIRS.split() if isinstance(PAIRS, str) else list(PAIRS)
    repo = os.environ['GITHUB_REPOSITORY']
    branch = 'claude-kevin-king'
    deadline = time.monotonic() + 150 * 60
    records = []
    completed = set()
    attempts = {p: 0 for p in pairs}
    output = Path('research-queue.json')

    def save():
        output.write_text(json.dumps({'completed': sorted(completed),
            'unfinished': [p for p in pairs if p not in completed],
            'attempts': attempts, 'runs': records}, indent=2))

    def consume(run_id, requested):
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('Queue time budget exhausted')
            state = json.loads(gh('run', 'view', str(run_id), '--repo', repo,
                '--json', 'status,conclusion'))
            if state['status'] == 'completed':
                break
            time.sleep(20)
        results = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                gh('run', 'download', str(run_id), '--repo', repo,
                   '--name', 'research-results-' + str(run_id), '--dir', directory)
                results = json.loads((Path(directory) / 'batch-report.json').read_text())['results']
        except (subprocess.CalledProcessError, OSError, ValueError, KeyError):
            pass
        # Publication must also succeed before a pair is considered finished.
        if state['conclusion'] == 'success':
            completed.update(set(requested) - set(pending_pairs(requested, results)))
        records.append({'run_id': str(run_id), **state, 'results': results})
        save()

    save()
    if existing:
        # Adopt the batch already started by the user, rather than duplicate it.
        initial = pairs[:4]
        for pair in initial:
            attempts[pair] += 1
        consume(existing, initial)
    while time.monotonic() < deadline:
        remaining = [p for p in pairs if p not in completed and attempts[p] < 2]
        if not remaining:
            break
        batch = remaining[:4]
        for pair in batch:
            attempts[pair] += 1
        save()
        # A unique run-name lets us identify this dispatch without guessing latest run.
        token = os.environ['GITHUB_RUN_ID'] + '-' + str(len(records))
        gh('workflow', 'run', 'research-study.yml', '--repo', repo, '--ref', branch,
           '-f', 'pairs=' + ','.join(batch), '-f', 'limit=4', '-f', 'offset=0',
           '-f', 'queue_token=' + token, '-F', 'publish=true')
        run_id = None
        for _ in range(18):
            runs = json.loads(gh('run', 'list', '--repo', repo, '--workflow',
                'research-study.yml', '--branch', branch, '--limit', '50',
                '--json', 'databaseId,displayTitle'))
            matches = [r for r in runs if r['displayTitle'] == 'Research batch ' + token]
            if matches:
                run_id = matches[0]['databaseId']
                break
            time.sleep(10)
        if run_id is None:
            raise RuntimeError('Dispatch not found; stopping to avoid duplicate work')
        consume(run_id, batch)
    save()
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write('## Research queue\nCompleted: ' + str(len(completed)) +
            '/' + str(len(pairs)) + '\n\nUnfinished: ' +
            (', '.join(p for p in pairs if p not in completed) or 'none') +
            '\n\nSee research-queue.json for individual runs and outcomes.\n')
    if len(completed) != len(pairs):
        raise SystemExit('Queue stopped with unfinished pairs; see queue artifact')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--existing', default='')
    main(parser.parse_args().existing)
