# Live trading bot

MT5-based live execution for the SLK strategy. Built after `backtest/`
validated the strategy's mechanics (see the repo root README) and after
an offline analysis (`simulate_v2_safe.py` + `account_audit_log.csv`,
not part of this repo -- ad hoc scratch work) established what prop-firm
risk rules actually hold up against real 2026 trade data, and what
doesn't (a naive "close everything when floating loss looks bad" rule
was tested and rejected -- it cost real money by cutting winners short).

## What's here

| Module | Job | MT5 dependency |
|---|---|---|
| `config.py` | Account/phase profiles -- prop_firm (phase1/phase2/funded, each with its own MT5 login + rule set) vs. personal (flat risk, no DD termination) | none |
| `risk_manager.py` | The actual risk gate: a deterministic pre-trade aggregate-risk check, a live equity circuit breaker, and a stop-slippage anomaly halt | none (works off `AccountState`, caller-supplied) |
| `audit_log.py` | SQLite decision log, schema matching `backtest/engine/trade_log.py`'s `TradeRecord` so backtest and live data share columns for future model training | none |
| `mt5_data.py` | Candle fetching, new-candle-close detection, account/position state, closed-deal lookup | yes -- injected, tested against a fake |
| `mt5_execution.py` | Lot sizing, order placement, slippage/spread/order-limit handling, retries | yes -- injected, tested against a fake |
| `live_cache_sync.py` | Keeps the on-disk candle cache fresh from MT5 so `run_backtest()` (completely unmodified) can be called live | yes -- injected, tested against a fake |
| `orchestrator.py` | The live loop tying all of the above together | via the above |
| `run_live.py` | The actual entry point -- the only file that imports the real `MetaTrader5` package | yes -- real, not injected |

## The core design decision

The strategy's entry-detection logic (`backtest/engine/runner.py`) is
built entirely around walking a full historical candle array -- bias
replay, structural sweep/break detection, `claimed_origins`
position-stacking state. Re-deriving that incrementally for live
"streaming" use would risk real behavioral drift from the
already-validated backtest path. Instead: `live_cache_sync.py` keeps the
on-disk cache `run_backtest()` already reads from topped up with fresh
MT5 candles (on the SAME `source="dukascopy"` series a one-time
bootstrap seeds with years of history, for the same lead-in structure/bias
detection needs), and the orchestrator just calls `run_backtest()`
itself, unmodified, on every new H1 candle close -- then checks whether
it produced a trade at that exact candle. Zero new strategy logic, zero
drift risk between what was backtested and what trades live.

## Setup

1. **Never commit credentials.** All MT5 logins come from environment
   variables (`_credentials_from_env()` in `config.py`), matching how
   `backtest/webapp/app.py` already handles its own secrets:
   - Prop firm: `MT5_PHASE1_LOGIN` / `_PASSWORD` / `_SERVER` (and
     `MT5_PHASE2_*` / `MT5_FUNDED_*` once those logins exist -- you won't
     have Phase 2's login yet while still trading Phase 1, and that's fine,
     only the active phase's credentials need to be set).
   - Personal: `MT5_PERSONAL_LOGIN` / `_PASSWORD` / `_SERVER`.

2. **Symbol suffix.** Check your MT5 terminal's Market Watch list against
   `backtest/data_pipeline/instruments.py`'s plain symbol names (EURUSD,
   XAUUSD, US30, ...). If your broker suffixes them (`EURUSD.a`,
   `EURUSDm`, etc.), pass `--symbol-suffix` to `run_live.py`.

3. **Demo first.** Test everything against a demo MT5 account before
   pointing this at a prop-firm evaluation or personal funded account --
   `mt5_data.py`, `mt5_execution.py`, and the closed-deal reconciliation
   in `orchestrator.py` are written against the documented `MetaTrader5`
   package API but have NOT been run against a real terminal from this
   development environment (no MT5 connectivity was reachable while
   writing this). `fetch_closed_deal()` in particular is the least
   verified piece -- confirm its behavior against your actual account's
   trade history before trusting the outcome logging.

4. **Run:**
   ```
   pip install -r bot/requirements.txt
   MT5_PHASE1_LOGIN=... MT5_PHASE1_PASSWORD=... MT5_PHASE1_SERVER=... \
       python -m bot.run_live --account-type prop_firm --phase phase1 \
       --instruments EURUSD,GBPUSD,USDJPY,XAUUSD --symbol-suffix .a
   ```

## Testing

`bot/tests/` -- 71 tests, all runnable without any MT5 connection
(`fake_mt5.py` mimics the real package's documented return shapes for
`mt5_data.py`/`mt5_execution.py`; everything else has no MT5 dependency
at all). Run with `python -m pytest bot/`.

What's tested: risk-gate math (including the aggregate-risk gate and the
anomaly/slippage halt), lot sizing and order-limit validation, retry
logic, candle conversion, cache sync/dedup, and the orchestrator's
decision routing (health checks, new-candle triggering, entry gating,
position reconciliation).

What's NOT verified by these tests, because nothing here can reach a
real MT5 terminal: the actual `MetaTrader5` package's connection
behavior, broker-specific quirks, real fill/slippage behavior, and
`history_deals_get()`'s exact real-world return shape.
