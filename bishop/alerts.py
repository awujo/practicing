"""Pure plain-text paper previews, never message transport."""
def format_alert(kind, row):
    details = row.get('details') or {}
    return '\n'.join([
        f"BISHOP · PAPER · {kind}",
        f"{row.get('instrument', '')} {row.get('side', '')} · {row.get('model', row.get('route', ''))}",
        'Key level: ' + str(row.get('level_id', details.get('level_id', 'see story'))),
        'Story so far: ' + str(row.get('state', row.get('status', kind))),
        'Context: ' + str(details.get('reason', row.get('reason', 'Recorded causal paper event'))),
        'Plan: ' + str(row.get('entry_ticks', '—')) + ' / stop ' + str(row.get('stop_ticks', '—')) + ' / target ' + str(row.get('target_ticks', '—')),
    ])
