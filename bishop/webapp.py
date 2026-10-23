"""Owner-only paper API. Import/create_app does not connect to external services."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from urllib.parse import parse_qsl

OWNER = '1410229777'


def validate_init_data(init_data, token, owner=OWNER, now=None, max_age=3600):
    if not init_data or not token or str(owner) != OWNER:
        raise ValueError('authentication unavailable')
    if len(init_data) > 16384:
        raise ValueError('invalid authentication')
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    if len({k for k, v in pairs}) != len(pairs):
        raise ValueError('duplicate authentication fields')
    values = dict(pairs)
    received = values.pop('hash', '')
    check = '\n'.join(f'{k}={v}' for k, v in sorted(values.items()))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise ValueError('invalid authentication')
    try:
        auth_date = int(values['auth_date'])
        user = json.loads(values['user'])
    except (ValueError, KeyError, TypeError):
        raise ValueError('invalid authentication') from None
    now = time.time() if now is None else now
    if auth_date <= 0 or not -30 <= now - auth_date <= max_age or str(user.get('id')) != OWNER:
        raise ValueError('authentication expired or owner mismatch')
    return user


def create_app(store=None, *, bot_token=None, local_api_key=None):
    from fastapi import FastAPI, Request, Depends, HTTPException
    from fastapi.responses import FileResponse
    from .paper_store import Store
    from . import settings
    # FastAPI evaluates annotations in module globals.
    globals()['Request'] = Request
    store = store if store is not None else Store(os.environ.get('BISHOP_PAPER_DB', ':memory:'))
    bot_token = bot_token if bot_token is not None else os.environ.get('TELEGRAM_BOT_TOKEN', '')
    app = FastAPI(title='Bishop Paper', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    static = Path(__file__).parent / 'web'

    def owner(request: Request):
        # Local key is accepted only when explicitly supplied to the factory and
        # the peer is loopback. Never use this mode in a remotely hosted service.
        provided = request.headers.get('X-Bishop-Owner-Key', '')
        if local_api_key and request.client and request.client.host in ('127.0.0.1', '::1') and hmac.compare_digest(provided, local_api_key):
            return {'id': int(OWNER)}
        try:
            return validate_init_data(request.headers.get('X-Telegram-Init-Data', ''), bot_token)
        except Exception:
            raise HTTPException(403, 'Owner authentication required') from None

    @app.middleware('http')
    async def bounds(request: Request, call_next):
        try:
            oversized = int(request.headers.get('content-length', '0')) > 65536
        except ValueError:
            oversized = True
        if len(request.url.query) > 8192 or oversized:
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Request too large'}, status_code=413)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/healthz')
    def health():
        return {'ok': True}

    @app.get('/')
    def index():
        return FileResponse(static / 'index.html')

    @app.get('/app.js')
    def script():
        return FileResponse(static / 'app.js', media_type='application/javascript')

    @app.get('/api/me')
    def me(user=Depends(owner)):
        return {'id': user['id'], 'mode': 'paper'}

    @app.get('/api/settings/schema')
    def schema(user=Depends(owner)):
        return settings.schema_json()

    @app.get('/api/settings')
    def get_settings(user=Depends(owner)):
        return store.get_settings()

    @app.patch('/api/settings')
    async def change(request: Request, user=Depends(owner)):
        try:
            body = await request.json()
            return store.change_settings(body['changes'], body['revision'])
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, 'Invalid settings or revision conflict') from None

    collections = {'bias': 'bias', 'entries': 'entries', 'orders': 'orders', 'history': 'events', 'runs': 'paper_runs', 'jobs': 'job_requests'}

    @app.get('/api/status')
    def status(user=Depends(owner)):
        return dict(mode='paper', delivery='DISABLED', scheduled=False, capabilities=settings.CAPABILITIES, runs=store.list('paper_runs', 10))

    @app.get('/api/results/summary')
    def summary(user=Depends(owner)):
        return {'runs': [{'id': r['id'], 'as_of': r['result']['as_of'], 'summary': r['result'].get('summary'), 'coverage': r['result']['coverage']} for r in store.list('paper_runs', 100)]}

    @app.post('/api/jobs')
    async def job(request: Request, user=Depends(owner)):
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError('object required')
            if set(body) - {'kind', 'input_reference', 'manifest_reference', 'as_of', 'history_start', 'scan_start', 'costs', 'examples_reference', 'management_actions'}:
                raise ValueError('unknown fields')
            if not isinstance(body.get('input_reference'), str) or len(body['input_reference']) > 1024:
                raise ValueError('input reference required')
            from .v2.types import utc
            utc(body['as_of'])
            from .runner import validate_management_actions
            validate_management_actions(body.get('management_actions', []))
            if not isinstance(body.get('manifest_reference'), str) or not isinstance(body.get('costs'), dict):
                raise ValueError('manifest and costs required')
            if body.get('kind') == 'replay' and not isinstance(body.get('examples_reference'), str):
                raise ValueError('examples reference required')
            return store.request_job(request.headers.get('Idempotency-Key', ''), body)
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, 'Invalid offline job request') from None

    @app.get('/api/{collection}')
    def listing(collection: str, limit: int = 100, offset: int = 0, user=Depends(owner)):
        if collection not in collections:
            raise HTTPException(404)
        return {'items': store.list(collections[collection], limit, offset), 'offset': max(offset, 0), 'limit': min(max(limit, 1), 500)}

    @app.get('/api/{collection}/{record_id}')
    def detail(collection: str, record_id: str, user=Depends(owner)):
        if collection not in collections:
            raise HTTPException(404)
        with store.lock:
            row = store._get(collections[collection], record_id)
        if row is None:
            raise HTTPException(404)
        return row

    @app.post('/cron/tick')
    def cron():
        raise HTTPException(403, 'External dispatch is disabled')

    return app
