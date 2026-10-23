"""Offline runner. No acquisition, workflow dispatch, broker or message calls."""
from .paper_store import Store


def persist_result(result, store, *, slot=None, namespace='paper'):
    return store.persist_result(result, slot or result['as_of'], namespace)


def run(*args, store=None, slot=None, namespace='paper', **kwargs):
    from .v2.engine import run as engine_run
    from . import settings
    store = store if store is not None else Store()
    effective = store.get_settings()['values']
    kwargs.setdefault('policy', settings.strategy_policy(effective))
    kwargs.setdefault('max_open_orders', effective['max_open_orders'])
    result = engine_run(*args, **kwargs)
    from .v2.types import jsonable
    result = jsonable(result)
    return persist_result(result, store, slot=slot, namespace=namespace)



def replay_observations(result):
    """Join actual execution to causal plans; interval fills retain a null exact time.

    Never consult teaching expectations. Legacy checker numeric fields require
    JSON numbers; tick precision and interval evidence remain in the full run.
    """
    from decimal import Decimal
    orders = {row['id']: row for row in result.get('orders', [])}
    setups = {row['id']: row for row in result.get('setups', [])}
    stories = {row['id']: row for row in result.get('stories', [])}
    instrument = result['instrument']
    tick = Decimal(str(instrument['tick_size']))
    exported = []
    for observation in result.get('observations', []):
        order = orders.get(observation.get('id'))
        if order is None:
            continue
        setup = setups.get(order['setup_id'], {})
        story = stories.get(setup.get('story_id'), {})
        window = observation.get('fill_window') or {}
        filled = observation.get('fill_ticks') is not None
        exact_time = window.get('start') if window.get('start') == window.get('end') else None
        risk = setup.get('risk_profile', result.get('policy', {}).get('risk_profile'))
        mode = {'owner_fixed11': 'aggressive_fixed_pips', 'context_liquidity': 'teacher_source_stop', 'source_structural': 'teacher_source_stop'}.get(risk, risk)
        pending_end = result['as_of']
        terminal_events = [e for e in result.get('execution_events', []) if e.get('reference_id') == order['id'] and e.get('kind') in ('ORDER_FILLED', 'ORDER_CANCELLED', 'ORDER_REPLACED', 'ORDER_EXPIRED')]
        if terminal_events:
            pending_end = min(e['clock']['available_at'] for e in terminal_events)
        def price(ticks):
            return float(Decimal(str(ticks)) * tick) if ticks is not None else None
        exported.append(dict(observation, pair=instrument['symbol'], tf=order['tf'],
            mode=mode, risk_profile=risk, mode_mapping='risk_to_legacy_replay_v1_implementation_policy', side=order['side'], status='FILLED' if filled else observation['status'],
            execution_status=observation['status'], time=exact_time if filled else None,
            observed_at=result['as_of'], pending_end=pending_end,
            setup_time=setup.get('clock', order['clock'])['available_at'],
            entry=price(observation.get('fill_ticks')), planned_entry=price(order['entry_ticks']), setup_entry=price(setup.get('entry_ticks')), actual_fill=price(observation.get('fill_ticks')), stop=price(order['stop_ticks']),
            target=price(order['target_ticks']),
            bias={'side': story.get('side'), 'tf': story.get('origin_tf')},
            fill_time_precision='EXACT' if exact_time else 'INTERVAL' if filled else 'UNFILLED'))
    return exported


def validate_management_actions(actions):
    """Validate explicit offline amendments; no action is inferred or submitted."""
    from decimal import Decimal, InvalidOperation
    from .v2.types import utc
    if not isinstance(actions, list) or len(actions) > 1000:
        raise ValueError('bounded management action list required')
    allowed = {'order_id', 'kind', 'available_at', 'at', 'occurred_at', 'reason', 'stop_ticks', 'target_ticks', 'price_ticks', 'quantity'}
    for action in actions:
        if not isinstance(action, dict) or set(action) - allowed:
            raise ValueError('unknown management fields')
        if not isinstance(action.get('order_id'), str) or not action['order_id'] or len(action['order_id']) > 128:
            raise ValueError('explicit stable order ID required')
        if action.get('kind') not in ('CANCEL', 'REPLACE', 'AMEND', 'BREAK_EVEN', 'PARTIAL', 'MANUAL_CLOSE'):
            raise ValueError('unsupported management action')
        utc(action.get('available_at', action.get('at')))
        if 'occurred_at' in action:
            utc(action['occurred_at'])
        for field in ('stop_ticks', 'target_ticks', 'price_ticks', 'quantity'):
            if field in action:
                try:
                    number = Decimal(str(action[field]))
                except InvalidOperation:
                    raise ValueError('invalid management number') from None
                if not number.is_finite() or (field == 'quantity' and number <= 0):
                    raise ValueError('invalid management number')
    return actions

def work_one(store, *, input_root, job_id=None):
    """Execute a queued job from explicitly declared local files only.

    Run this worker manually; the application never starts a background worker.
    Long historical tasks need a suitable explicit lease_seconds at claim time.
    """
    import json
    from pathlib import Path
    from . import settings
    from .v2.types import utc
    root = Path(input_root).resolve(strict=True)
    def local(value):
        if not isinstance(value, str) or '://' in value:
            raise ValueError('declared local file required')
        path = (root / value).resolve(strict=True)
        if root not in path.parents or not path.is_file():
            raise ValueError('input outside allowed root')
        return path
    job = store.claim_job(job_id)
    if job is None:
        return None
    token = job['lease_token']
    try:
        request = job['request']
        feed = local(request['input_reference'])
        manifest = local(request['manifest_reference'])
        as_of = utc(request['as_of'])
        costs = request['costs']
        if not isinstance(costs, dict) or set(costs) != {'spread_ticks', 'entry_slippage_ticks', 'stop_slippage_ticks', 'commission_ticks', 'financing_ticks'}:
            raise ValueError('all cost hypotheses must be explicit')
        from .v2.simulation import Costs
        declared_costs = Costs(**costs)
        policy = settings.strategy_policy(job['settings']['values'])
        from .v2.engine import run as engine_run
        result = engine_run(feed, manifest, as_of=as_of,
            history_start=request.get('history_start'), scan_start=request.get('scan_start'),
            policy=policy, costs=declared_costs,
            max_open_orders=job['settings']['values']['max_open_orders'],
            management_actions=validate_management_actions(request.get('management_actions', [])))
        from .v2.types import jsonable
        result = jsonable(result)
        acceptance = None
        if request['kind'] == 'replay':
            from .replay import evaluate
            examples = json.loads(local(request['examples_reference']).read_text())
            exported = replay_observations(result)
            acceptance = evaluate(examples, exported)
            acceptance['observation_export'] = exported
            acceptance['limitations'] = ['Interval fills retain null exact times and cannot pass the exact-time checker.', 'Missing source-profile equivalence remains a comparison limitation.']
        # Different jobs/settings never rewrite the ongoing paper namespace.
        record = persist_result(result, store, slot=job['id'], namespace='job:' + job['id'])
        return store.finish_job(job['id'], token, result_id=record['id'], acceptance=acceptance)
    except Exception as exc:
        # No secret-bearing paths, payloads or exception strings in persisted errors.
        return store.finish_job(job['id'], token, error=type(exc).__name__)


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description='Persist a locally computed Bishop paper result; no acquisition')
    parser.add_argument('--result')
    parser.add_argument('--work-one', action='store_true')
    parser.add_argument('--input-root')
    parser.add_argument('--job-id')
    parser.add_argument('--database', required=True)
    parser.add_argument('--slot')
    parser.add_argument('--namespace', default='paper')
    args = parser.parse_args(argv)
    if args.work_one:
        if not args.input_root:
            parser.error('--input-root is required for offline job execution')
        print(json.dumps(work_one(Store(args.database), input_root=args.input_root, job_id=args.job_id)))
        return 0
    if not args.result:
        parser.error('--result or --work-one is required')
    with open(args.result) as stream:
        result = json.load(stream)
    row = persist_result(result, Store(args.database), slot=args.slot, namespace=args.namespace)
    print(json.dumps(dict(id=row['id'], status=row['result']['status'], delivery='DISABLED')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
