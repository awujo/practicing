# Bishop bot rebuild

Branch: `claude-bishop-aggressive`. Current stage: source verification and
acceptance infrastructure. No completed Bishop trading engine or live deployment
exists yet. Passing unit tests does not mean teaching examples match.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
python -m bishop.store --help
```

The Bishop development checks Action runs offline tests without production
credentials. It does not send alerts or execute broker orders.

## Example acceptance

`tests/bishop_examples.json` preserves teacher observations independently of bot
results. Initial PDF observations remain unresolved until exact UTC trade times,
feed alignment, and source-derived tolerances are established. Image creation
dates are not entry times. Position-tool stop edges alone do not independently
identify imbalance edges.

Once an engine exports real observations:

```bash
python -m bishop.replay --observations path/to/engine-observations.json
```

Observations are a JSON list with `pair`, `tf`, `mode`, timezone-aware ISO `time`,
`side`, `status`, `entry`, `stop`, and `target`, plus `bias: {side, tf}` and the
timezone-aware `setup_time` when the setup became available. Executed entries use `FILLED`;
explicit evaluated no-trade decisions use `NO_TRADE`.

One filled observation must match all expected fields simultaneously, including
timeframe and target. Tolerances must come from source measurement resolution.
Empty/unresolved coverage or any mismatch returns nonzero. Never copy source
expectations into an observation file as a substitute for running an engine.
Teacher-demonstrated stops/targets and the aggressive operating preset remain
separate; fixed 10–11-pip settings cannot replace different source stops.

## Evidence

- [Strategy](knowledge-base/STRATEGY.md)
- [Course ledger](knowledge-base/study/course_verified.md)
- [Bishop ledger](knowledge-base/study/bishop_verified.md)
- [Plug-and-play ledger](knowledge-base/study/plug_verified.md)
- [Independent source cross-check](knowledge-base/study/source_crosscheck.md)
- [Chart evidence](knowledge-base/study/examples_evidence.md)
- [Independent code review](reference/BUILD_REVIEW.md)
- [Handoff](HANDOVER.md)

The candle layer uses the inherited New York 17:00 FX session convention.
`candles.completed` excludes forming H1 and higher-timeframe bars using calendar
closes. Feed completeness and teacher-feed compatibility require separate checks.
Weekend-traded assets need a separate session policy.

Shared Kevin cTrader tokens stay read-only through database and memory fallback
paths. Only an explicit empty `CTRADER_TOKEN_TABLE` selects independently owned
tokens. The initial schema creates `bishop_settings` and `bishop_runs` only.
