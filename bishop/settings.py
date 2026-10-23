"""Public paper settings. Secrets and activation capabilities are never settings."""
import hashlib
import json

SCHEMA = [
    dict(name='risk_profile', type='choice', default='owner_aggressive_fixed11', choices=['source', 'owner_aggressive_fixed11', 'zone_edge'], group='Risk', help='Owner aggressive fixed 11 default, source protection, or the disclosed zone-edge experiment.'),
    dict(name='pending_expiry_minutes', type='integer', default=1440, minimum=1, maximum=43200, group='Orders', help='Operating policy, not teacher invalidation.'),
    dict(name='max_open_orders', type='integer', default=10, minimum=1, maximum=1000, group='Orders', help='Prospective paper exposure cap.'),
    dict(name='display_timezone', type='timezone', default='UTC', group='Display', help='Display only; processing uses UTC.'),
]
SCHEMA += [
    dict(name='source_profile', type='choice', default='owner_aggressive', choices=['bishop_confirmation', 'nested_confirmation', 'source_all', 'owner_aggressive', 'plug_and_play', 'core_course'], group='Source models', help='Prospective source model; unavailable routes remain reported.'),
    dict(name='oc_gap_ticks', type='integer', default=0, minimum=0, maximum=100000, group='Numerical policies', help='Explicit OC gap tolerance in ticks.'),
    dict(name='impulse_atr_fraction', type='nullabledecimal', default=None, group='Numerical policies', help='Unknown by default; enter a positive experimental ATR impulse threshold, or leave blank.'),
    dict(name='impulse_atr_period', type='integer', default=20, minimum=1, maximum=1000, group='Numerical policies', help='Closed-bar ATR window for an explicitly chosen impulse experiment.'),
    dict(name='near_atr_period', type='integer', default=20, minimum=1, maximum=1000, group='Numerical policies', help='Closed-bar arithmetic ATR window.'),
    dict(name='near_atr_fraction', type='decimal', default='0.25', group='Numerical policies', help='Named proximity experiment, not a universal teaching constant.'),
    dict(name='stop_buffer_units', type='decimal', default='0.5', group='Risk', help='Structural protection buffer in declared instrument distance units.'),
    dict(name='fallback_rejections', type='integer', default=1, minimum=1, maximum=100, group='Source models', help='Explicit fallback rejection policy.'),
    dict(name='allow_counterweekly', type='boolean', default=True, group='Source models', help='Allow the disclosed counterweekly model.'),
    dict(name='entry_tfs', type='timeframes', default=['H4','H3','H2','H1','M45','M30','M15','M5'], group='Source models', help='Prospective entry timeframes; base input must support them.'),
    dict(name='origin_tfs', type='timeframes', default=['M','W','D','H4'], group='Source models', help='Prospective story origin timeframes.'),
]
DEFAULTS = {s['name']: s['default'] for s in SCHEMA}
CAPABILITIES = dict(execution_mode='paper', network_acquisition=False, telegram_delivery=False, external_dispatch=False, scheduled_execution=False)


def validate(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError('unknown settings')
    result = dict(DEFAULTS)
    result.update(values)
    for spec in SCHEMA:
        value = result[spec['name']]
        if spec['type'] == 'choice' and value not in spec['choices']:
            raise ValueError('invalid choice')
        if spec['type'] == 'integer' and (type(value) is not int or not spec['minimum'] <= value <= spec['maximum']):
            raise ValueError('invalid integer')
        if spec['type'] == 'nullabledecimal' and value is None:
            continue
        if spec['type'] in ('decimal', 'nullabledecimal'):
            from decimal import Decimal, InvalidOperation
            try:
                number = Decimal(str(value))
                if not number.is_finite() or not 0 <= number <= 10000 or (spec['type'] == 'nullabledecimal' and number <= 0):
                    raise ValueError('invalid decimal')
            except InvalidOperation:
                raise ValueError('invalid decimal') from None
            result[spec['name']] = str(number)
        if spec['type'] == 'boolean' and type(value) is not bool:
            raise ValueError('invalid boolean')
        if spec['type'] == 'timeframes':
            allowed = {'M','W','D','H4','H3','H2','H1','M45','M30','M15','M5'}
            if not isinstance(value, list) or not value or any(v not in allowed for v in value) or len(set(value)) != len(value):
                raise ValueError('invalid timeframes')
        if spec['type'] == 'timezone':
            from zoneinfo import ZoneInfo
            if not isinstance(value, str):
                raise ValueError('invalid timezone')
            try:
                ZoneInfo(value)
            except Exception:
                raise ValueError('invalid timezone') from None
    return result


def snapshot(values):
    effective = validate(values)
    encoded = json.dumps(effective, sort_keys=True, separators=(',', ':'))
    return dict(values=effective, hash=hashlib.sha256(encoded.encode()).hexdigest(), capabilities=CAPABILITIES)


def schema_json():
    return dict(settings=SCHEMA, capabilities=CAPABILITIES, source_profiles=['bishop_confirmation', 'nested_confirmation', 'source_all', 'owner_aggressive', 'plug_and_play', 'core_course'], qualification='Engineering paper results; historical teaching acceptance remains separate.')


def strategy_policy(values):
    """Translate public source/owner choices to the shared immutable engine policy."""
    from .v2.types import StrategyPolicy
    values = validate(values)
    names = ('source_profile', 'oc_gap_ticks', 'near_atr_period', 'near_atr_fraction',
             'stop_buffer_units', 'fallback_rejections', 'allow_counterweekly',
             'entry_tfs', 'origin_tfs', 'impulse_atr_fraction', 'impulse_atr_period')
    return StrategyPolicy(**{name: values[name] for name in names},
        risk_profile={'owner_aggressive_fixed11': 'owner_fixed11', 'source': 'context_liquidity', 'zone_edge': 'zone_edge'}[values['risk_profile']],
        fixed_stop_units='11', pending_minutes=values['pending_expiry_minutes'])
