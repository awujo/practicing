"""Transactional isolated paper persistence; no network unless MySQL explicitly requested."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import threading
from . import settings

TABLES = ('paper_runs', 'bias', 'entries', 'orders', 'events', 'outbox', 'job_requests', 'paper_settings')


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def ident(*parts):
    return hashlib.sha256(encode(parts).encode()).hexdigest()


class Store:
    def __init__(self, path=':memory:', *, mysql_url=None, migrate=False):
        self.lock = threading.RLock()
        self.mysql = mysql_url is not None
        if self.mysql:
            from .db import connect
            self.connection = connect(mysql_url)
            self.connection.autocommit(False)
        else:
            self.connection = sqlite3.connect(path, check_same_thread=False)
            self.connection.row_factory = sqlite3.Row
        if not self.mysql or migrate:
            self.migrate()

    def _execute(self, sql, args=()):
        if self.mysql:
            cur = self.connection.cursor()
            cur.execute(sql.replace('?', '%s'), args)
            return cur
        return self.connection.execute(sql, args)

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                self._execute('START TRANSACTION' if self.mysql else 'BEGIN IMMEDIATE')
                yield
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise

    def migrate(self):
        # Separate names avoid the legacy bishop_settings/runs schema entirely.
        with self.transaction():
            for name in TABLES:
                self._execute(f'CREATE TABLE IF NOT EXISTS bishop_{name} (id VARCHAR(128) PRIMARY KEY, payload MEDIUMTEXT NOT NULL)')
            if self._get('paper_settings', 'current') is None:
                self._put('paper_settings', 'current', dict(revision=0, values=settings.DEFAULTS))

    def _get(self, table, key, lock=False):
        assert table in TABLES
        suffix = ' FOR UPDATE' if lock and self.mysql else ''
        row = self._execute(f'SELECT payload FROM bishop_{table} WHERE id=?' + suffix, (key,)).fetchone()
        return json.loads(row['payload']) if row else None

    def _put(self, table, key, value):
        assert table in TABLES
        if self._get(table, key) is not None:
            self._execute(f'UPDATE bishop_{table} SET payload=? WHERE id=?', (encode(value), key))
        else:
            self._execute(f'INSERT INTO bishop_{table} (id,payload) VALUES (?,?)', (key, encode(value)))

    def list(self, table, limit=100, offset=0):
        if table not in TABLES:
            raise ValueError('invalid collection')
        with self.lock:
            rows = self._execute(f'SELECT payload FROM bishop_{table} ORDER BY id LIMIT ? OFFSET ?', (max(1, min(int(limit), 500)), max(0, int(offset)))).fetchall()
            return [json.loads(r['payload']) for r in rows]

    def get_settings(self):
        with self.lock:
            row = self._get('paper_settings', 'current')
            return dict(revision=row['revision'], **settings.snapshot(row['values']))

    def change_settings(self, changes, revision):
        with self.transaction():
            row = self._get('paper_settings', 'current', lock=True)
            if type(revision) is not int or row['revision'] != revision:
                raise ValueError('settings revision conflict')
            merged = dict(row['values'])
            merged.update(changes)
            values = settings.validate(merged)
            updated = dict(revision=revision + 1, values=values)
            self._put('paper_settings', 'current', updated)
            self._put('events', ident('settings', revision + 1), dict(kind='SETTINGS_CHANGED', **updated))
        return self.get_settings()

    def request_job(self, key, job):
        if job.get('kind') not in ('scan', 'backtest', 'replay'):
            raise ValueError('unsupported job')
        if not isinstance(key, str) or not 1 <= len(key) <= 100:
            raise ValueError('idempotency key required')
        with self.transaction():
            existing = self._get('job_requests', key)
            if existing:
                if existing['request'] != job:
                    raise ValueError('idempotency key conflict')
                return existing
            row = dict(id=key, status='QUEUED_OFFLINE', request=job, settings=self._get('paper_settings', 'current'))
            self._put('job_requests', key, row)
            return row

    def persist_result(self, result, slot, namespace='paper'):
        from .alerts import format_alert
        required = ('status', 'as_of', 'instrument', 'input', 'policy', 'coverage')
        if not ('schema' in result or 'schema_version' in result) or any(k not in result for k in required):
            raise ValueError('incomplete engine result')
        from .v2.types import utc
        as_of = utc(result['as_of'])
        observations = {row['id']: row for row in result.get('observations', []) if row.get('id')}
        positions = {row['order_id']: row for row in result.get('positions', []) if row.get('order_id')}
        run_id = ident(namespace, slot)
        digest = ident(result)
        with self.transaction():
            previous = self._get('paper_runs', run_id)
            if previous:
                if previous['result_hash'] != digest:
                    raise ValueError('slot already committed with different result')
                return previous
            # Projections and immutable event history commit with the run.
            for field, table in (('stories', 'bias'), ('setups', 'entries'), ('orders', 'orders')):
                for row in result.get(field, []):
                    if not row.get('id'):
                        raise ValueError('causal record ID required')
                    key = ident(namespace, row['id'])
                    existing = self._get(table, key, lock=True)
                    if existing and existing.get('_projection_as_of') and utc(existing['_projection_as_of']) > as_of:
                        continue  # Historical results remain in runs/events; never regress the current card.
                    projection = dict(row, namespace=namespace, _projection_as_of=as_of.isoformat())
                    if table == 'orders':
                        observation = observations.get(row['id'], {})
                        projection.update(observation)
                        projection['status'] = observation.get('status', row.get('status', 'PENDING'))
                        if row['id'] in positions:
                            projection['position'] = positions[row['id']]
                    self._put(table, key, projection)
            for field in ('story_events', 'execution_events'):
                for row in result.get(field, []):
                    if not row.get('id'):
                        raise ValueError('event ID required')
                    key = ident(namespace, row['id'])
                    existing = self._get('events', key)
                    if existing and existing != row:
                        raise ValueError('immutable event conflict')
                    self._put('events', key, row)
                    self._put('outbox', key, dict(id=key, status='DISABLED', text=format_alert(row.get('kind', 'UPDATE'), row)))
            run = dict(id=run_id, namespace=namespace, slot=slot, result_hash=digest, result=result, committed_at=datetime.now(timezone.utc).isoformat())
            self._put('paper_runs', run_id, run)
            return run

    def claim_job(self, job_id=None, lease_seconds=900):
        """Claim one queued or expired job. Token fences stale worker completion."""
        import time
        import uuid
        with self.transaction():
            candidates = ([self._get('job_requests', job_id, lock=True)] if job_id else self.list('job_requests', 500))
            for candidate in candidates:
                if not candidate:
                    continue
                row = self._get('job_requests', candidate['id'], lock=True)
                if row['status'] != 'QUEUED_OFFLINE' and not (row['status'] == 'RUNNING' and row.get('lease_until', 0) <= time.time()):
                    continue
                row.update(status='RUNNING', lease_token=uuid.uuid4().hex, lease_until=time.time() + lease_seconds)
                self._put('job_requests', row['id'], row)
                return row
        return None

    def finish_job(self, job_id, token, *, result_id=None, error=None, acceptance=None):
        import time
        with self.transaction():
            row = self._get('job_requests', job_id, lock=True)
            if not row or row.get('lease_token') != token or row['status'] != 'RUNNING' or row.get('lease_until', 0) <= time.time():
                raise ValueError('job lease lost')
            row.update(status='FAILED' if error else 'COMPLETED', result_id=result_id,
                       error=error, acceptance=acceptance, lease_until=0)
            self._put('job_requests', job_id, row)
            return row
