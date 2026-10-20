# Bishop bot rebuild

Branch: `claude-bishop-aggressive`. Current stage: an initial offline causal
engine, paper execution simulator and source verification. The full Bishop bot
and live deployment remain unfinished. Passing unit tests does not mean teaching
examples match.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
python -m bishop.store --help
```

The Bishop development checks Action runs offline tests without production
credentials. It does not send alerts or execute broker orders.

## Initial offline engine

The engine currently supports KL rejection/prior-candle sweep followed by a
closed lower-TF breakout, then engulf/retest or OC-break/retest candidates.
Local structural references, level interpretation and context retirement are
explicit implementation choices. Targets are opposing origin-TF KLs; nearest
ERL selection and the aggressive direct-entry models are still unsupported.
Candidate alternatives are unranked; their sum is not a portfolio return or a
claim that every alternative should be traded.

Reproduce the small frozen-input engineering comparison:

```bash
python -m reports.reproduce_initial_study
```

This uses the retained IC Markets EURGBP BID export and declared assumptions
(1-pip spread, 0.2-pip stop slippage, 0.5-pip round-trip commission). Reports
record the input hash, engine hash, runtime versions, coverage and exact policy
choices. This script completes an engineering study; teacher acceptance remains
UNRESOLVED. See [the result](reports/ENGINE_MILESTONE.md).

The `python -m bishop.backtest --help` CLI requires explicit input/source,
historical clock, warmup/scan range, timeframes, level/stop policy, costs and
pending expiry. Add `--examples tests/bishop_examples.json` to apply the hard
acceptance gate; unresolved or mismatched source cases return nonzero.

H1 execution separates setup availability, a fill-bar interval, the first
observation of a fill and the current observation clock. A partial active bar,
missing market hour or ambiguous fill-bar target cannot become an invented
precise execution. No complete-history claim is made from partial cache data.
See [review coverage and open limits](reference/ENGINE_REVIEW.md).

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

This first checker supports executed trades and no-trade decisions. Teaching
plans, pending orders and misses must retain their actual demonstrated state;
they stay unresolved until a corresponding acceptance category is implemented.
They must never be relabelled as filled trades to obtain a match.

One filled observation must match all expected fields simultaneously, including
timeframe and target. Tolerances must come from source measurement resolution.
Empty/unresolved coverage or any mismatch returns nonzero. Never copy source
expectations into an observation file as a substitute for running an engine.
Teacher-demonstrated stops/targets and the aggressive operating preset remain
separate; fixed 10–11-pip settings cannot replace different source stops.

## Evidence

Frame sampling previously selected later video frames while burning earlier
timestamps. The extractor now records actual source presentation times; corrected
Bishop re-extraction is tracked in the frame manifest. Original course and
plug-and-play sheets still require regeneration before their labels can support
exact-time citations. Native timestamp-verified snapshots remain separate evidence.

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
