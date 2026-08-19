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
| `run_live.py` | The actual entry point -- the only file that connects to a real MT5 (directly, or via the `mt5linux` bridge for an Ubuntu VPS) | yes -- real, not injected |

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
   - Never paste real credentials into a chat/screenshot to hand them to
     someone (including an assistant) -- set them directly as env vars on
     the machine that's going to use them. A demo account is low-stakes;
     build the habit before it's a prop-firm or funded login.

2. **Symbol suffix.** Check MT5's Market Watch search for each of
   `backtest/data_pipeline/instruments.py`'s plain symbol names (EURUSD,
   XAUUSD, US30, NAS100, JP225, ETHUSD, USOIL, ...) -- forex majors and
   indices/metals/crypto sometimes get different suffix treatment even on
   the SAME server, so checking only one or two forex pairs isn't enough
   to conclude there's no suffix anywhere. Set `--symbol-suffix` (or
   `MT5_SYMBOL_SUFFIX`) to whatever's actually there.

3. **Demo first.** Test everything against a demo MT5 account before
   pointing this at a prop-firm evaluation or personal funded account --
   `mt5_data.py`, `mt5_execution.py`, and the closed-deal reconciliation
   in `orchestrator.py` are written against the documented `MetaTrader5`
   package API but have NOT been run against a real terminal from this
   development environment (no MT5 connectivity was reachable while
   writing this). `fetch_closed_deal()` in particular is the least
   verified piece -- confirm its behavior against your actual account's
   trade history before trusting the outcome logging. The `mt5linux`
   bridge (see below) is its own additional layer of "not verified from
   here" on top of that.

4. **Run** (after the Ubuntu VPS setup below, or directly if you're
   already on Windows with `--bridge native`):
   ```
   pip install -r bot/requirements.txt
   MT5_PHASE1_LOGIN=... MT5_PHASE1_PASSWORD=... MT5_PHASE1_SERVER=... \
       python -m bot.run_live --account-type prop_firm --phase phase1 \
       --instruments EURUSD,GBPUSD,USDJPY,XAUUSD --symbol-suffix ""
   ```

## Ubuntu VPS setup (mt5linux bridge)

MT5 has no native Linux client and the `MetaTrader5` Python package has
no Linux wheels, so this needs two pieces running side by side: the real
MT5 terminal + a Windows Python under Wine (where `MetaTrader5` actually
works), and this repo's normal native-Linux Python talking to it through
`mt5linux`'s bridge server. Run this in its own directory/venv, isolated
from whatever else is already on the VPS:

```bash
# 1. Wine + the MT5 terminal
sudo dpkg --add-architecture i386 && sudo apt update
sudo apt install -y wine wine32 winbind
winecfg   # first run creates ~/.wine -- accept the defaults (Windows 10)
wget https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe
wine mt5setup.exe   # click through the installer

# 2. A Windows Python inside that same Wine prefix, and the real
#    MetaTrader5 package installed INTO it (not your system Python)
wget https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
wine python-3.11.9-amd64.exe   # click through, note the install path
wine "C:\Users\$USER\AppData\Local\Programs\Python\Python311\python.exe" -m pip install MetaTrader5 mt5linux

# 3. Start the bridge server (leave this running -- tmux/screen/systemd,
#    not your interactive shell, since it needs to survive logout)
wine "C:\Users\$USER\AppData\Local\Programs\Python\Python311\python.exe" -m mt5linux

# 4. Native Linux side: this repo's own venv, separate from other
#    projects on the VPS
cd /path/to/trading
python3 -m venv .venv-bot && source .venv-bot/bin/activate
pip install -r backtest/data_pipeline/requirements.txt -r bot/requirements.txt
MT5_PHASE1_LOGIN=... MT5_PHASE1_PASSWORD=... MT5_PHASE1_SERVER=MetaQuotes-Demo \
    python -m bot.run_live --account-type prop_firm --phase phase1 \
    --instruments EURUSD,GBPUSD,USDJPY,XAUUSD --symbol-suffix "" \
    --bridge mt5linux --bridge-host 127.0.0.1 --bridge-port 18812
```

This whole sequence is written from `mt5linux`/Wine's documented usage
patterns, not run end-to-end from this development environment -- exact
paths, package versions, and the bridge server's startup behavior will
need real troubleshooting on your actual VPS. Expect the first attempt
not to work cleanly; that's normal for a Wine-based bridge like this, not
a sign something in `bot/`'s own code is wrong.

## Testing

`bot/tests/` -- 90 tests, all runnable without any MT5 connection
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
