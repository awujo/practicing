# Bishop offline v2

This package implements the source-informed build separately from the legacy
`bishop.engine`. The full-study synthesis and contracts in
`knowledge-base/study/` explain the teaching evidence and numerical choices.
Computing a setup does not establish that it matches a teacher example.

The pipeline is local feed validation → complete calendar aggregation →
close-line structure and independent wick liquidity → scoped stories → entry
families and risk → prospective order selection → strict OHLC execution.
All events separate occurrence from availability. Missing data resets causal
segments; an ambiguous executable candle is censored rather than assigned a
favourable sequence. There are no data acquisition, token-refresh, broker,
message-delivery or deployment calls in this package.

## Run

Use an existing frozen CSV or gzip CSV with `start` (or `time`), `open`, `high`,
`low`, `close`; optional `end` and `available_at` are aware UTC timestamps.
Prices must lie on the declared tick grid. The manifest must explicitly supply:

```json
{
  "symbol": "EURUSD",
  "tick_size": "0.00001",
  "distance_unit": "0.0001",
  "calendar_id": "fx_ny_v1",
  "anchor_id": "ny17_wall_v2",
  "price_basis": "BID",
  "source_id": "your-frozen-source-version",
  "venue": "your-provider",
  "base_tf": "M1"
}
```

These values describe an input, not an instruction to download that input.
Optionally supply `sha256` of the original file bytes (compressed bytes for
gzip). Custom calendar intervals are declared through `calendar`.

Declare all execution costs in a separate JSON file. Explicit zeros describe a
zero-cost hypothesis, not a broker cost estimate:

```json
{
  "spread_ticks": "0",
  "entry_slippage_ticks": "0",
  "stop_slippage_ticks": "0",
  "commission_ticks": "0",
  "financing_ticks": "0"
}
```

```bash
python -m bishop.v2.backtest --feed /path/frozen.csv.gz \
  --manifest /path/manifest.json --costs /path/costs.json \
  --as-of 2026-01-15T00:00:00Z --output /path/result.json
```

`--history-start` controls context; `--scan-start` controls new setup eligibility.
Supply `--policy` for a JSON object of `StrategyPolicy` fields, and
`--management-actions` for explicit simulator actions referencing causal order
IDs. Actions include cancellation, replacement, break-even, amendment, partial
and manual close. Closed positions retain their original order plan and event
history. Historical jobs use isolated persistence namespaces.

## Source selection

- `bishop_confirmation`: reaction confirmation families; this is the default.
- `owner_aggressive`: direct H4/H2 and aggressive KL/imbalance alternatives.
- `core_course`: engulf/A-V, OC and IRL retests.
- `plug_and_play`: the explicitly selected plug/direct alternatives.
- `nested_confirmation`: the declared H4/H1/lower-timeframe chain.
- `source_all`: independent diagnostic alternatives, never a combined portfolio.

New paper stores default to the owner aggressive/fixed-11 preset; existing
saved settings remain unchanged. The library default is source-confirmation.
The fixed stop experiment is separate: `risk_profile="owner_fixed11"` uses 11
instrument distance units. Library default `context_liquidity` protects known source
objects. A missing stop or target leaves the setup `UNRESOLVED`; it does not
receive an invented risk plan. Selectable `zone_edge` uses the explicit FVG
far edge plus buffer only for known FVG setups; it is an owner experiment, not
a universal source stop rule. `nearest_erl`, `story_destination` and fixed 3R
are distinct target policies. Numeric OC tolerance, near-touch ATR, expiry and
buffers are declared implementation choices.

Core/plug flipped-role routes require positive impulse qualification.
`impulse_atr_fraction=null` deliberately leaves unqualified raw breaks unknown.
An explicitly supplied positive fraction enables the named body/prior-ATR
hypothesis with `impulse_atr_period` (default 20). It is not a teacher-defined
threshold and never gates all raw breaks.

Session pools require an explicit manifest `sessions` list, for example
`[{"id":"declared_session","timezone":"Europe/London","start":"00:00",
"end":"06:00","weekdays":[0,1,2,3,4],"tf":"H4"}]`. No Asian-session hours
are inferred. Incomplete sessions produce diagnostics, not extrema. Ambiguous
DST boundaries require explicit `dst_fold`; nonexistent boundaries are rejected.

## Interpretation and limits

`COMPUTED_UNVALIDATED` means the computation ran with base coverage;
`PARTIAL_UNVALIDATED` identifies empty, missing or insufficient-resolution input.
Per-timeframe diagnostics also identify forming and incomplete aggregate bins.
Teacher acceptance remains `NOT_REPLAYED` until a separate strict source replay.
A higher-resolution input is required for requested lower timeframes; H1 candles
cannot produce M5 evidence. The executable simulator currently supports BID
input with a declared spread hypothesis; other price bases fail explicitly.

The paper app persists full deterministic snapshots, immutable events, disabled
outbox records and manual offline jobs. It does not provide a continuously
running incremental detector or active broker execution. See
`knowledge-base/study/build_paper_app_contract.md` for app and worker commands.
Discretionary source exceptions and the uncertain PDF p8 standing-extreme
referent remain explicit support gaps. Uncertain source labels, missing exact
fill times and unavailable historical feeds cannot be converted into matches
by changing expectations or copying teacher prices into this engine.
