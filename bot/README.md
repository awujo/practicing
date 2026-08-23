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

2. **Symbol mapping.** Check MT5's Market Watch search for each of
   `backtest/data_pipeline/instruments.py`'s plain symbol names (EURUSD,
   XAUUSD, US30, NAS100, JP225, ETHUSD, USOIL, ...). A suffix isn't
   always the whole story -- confirmed on MetaQuotes-Demo: forex majors/
   crosses and metals are all plain (no suffix), but `NAS100` doesn't
   exist there at all -- it's `USTEC` -- and `JP225` is `JPN225`. `USOIL`
   and `ETHUSD` are still unconfirmed on that server; check Energy/Crypto
   categories before trading either. `config.SymbolMap` handles both
   cases: `--symbol-suffix` (`MT5_SYMBOL_SUFFIX`) for a plain suffix
   applied to everything, `--symbol-overrides` (`MT5_SYMBOL_OVERRIDES`,
   JSON) for symbols that are renamed outright -- overrides win when both
   would apply to the same symbol. `run_live.py`'s `METAQUOTES_DEMO_OVERRIDES`
   constant holds the confirmed mapping for that specific server; it's
   never applied automatically since a real prop firm's broker will very
   likely need a different one.

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
       --instruments EURUSD,GBPUSD,USDJPY,XAUUSD,NAS100,JP225 \
       --symbol-overrides '{"NAS100": "USTEC", "JP225": "JPN225"}'
   ```

## Ubuntu VPS setup (mt5linux bridge)

MT5 has no native Linux client and the `MetaTrader5` Python package has
no Linux wheels, so this needs two pieces running side by side: the real
MT5 terminal + a Windows Python under Wine (where `MetaTrader5` actually
works), and this repo's normal native-Linux Python talking to it through
`mt5linux`'s bridge server. This section reflects what actually worked,
end to end, against a real VPS and a real MetaQuotes-Demo account --
a manual `wine mt5setup.exe` install was tried first and abandoned after
hours of a stuck installer with no clear cause; the Docker route below
worked on the first real attempt.

```bash
# 1. The MT5 terminal + Wine + a KasmVNC browser-viewable desktop, all in
#    one prebuilt image -- avoids the manual Wine/Xvfb dance entirely.
#    Pick a host port for the noVNC viewer that doesn't collide with
#    anything else already running (check `docker ps` / `ss -tlnp` first).
docker run -d --name mt5 -p 18080:3000 gmag11/metatrader5_vnc
# Watch it install (Wine, the MT5 terminal, a Wine-side Python) via:
docker logs -f mt5
# Then open http://<vps-ip>:18080 in a browser -- you'll see the actual
# MT5 desktop. Click through the first-run "Select a company to open an
# account with" dialog (MetaQuotes Ltd.) and log in with your demo
# credentials there, same as you would on a real desktop.

# 2. mt5linux: the image ships a NEWER version (1.1.1 as of writing) that
#    has genuine Python-3.12-only syntax in a 3.12-targeted rewrite --
#    fails with a SyntaxError on this image's Python 3.11. Downgrade to
#    the older, simpler RPyC-bridge version on BOTH sides:
docker exec -u abc mt5 pip3 install --break-system-packages "mt5linux<1.0"   # Linux side
docker exec -u abc mt5 wine "C:\Program Files (x86)\Python39-32\python.exe" \
    -m pip install "mt5linux<1.0"                                            # Wine side

# 3. numpy 2.x breaks the real MetaTrader5 package's compiled _core on
#    the Wine side (built against numpy<2):
docker exec -u abc mt5 wine "C:\Program Files (x86)\Python39-32\python.exe" \
    -m pip install "numpy<2"

# 4. Start the bridge server on the Wine side (tmux, not your interactive
#    shell -- a dropped SSH session killing this is exactly what cost
#    hours during initial setup):
tmux new -s bridge1
docker exec -u abc mt5 wine "C:\Program Files (x86)\Python39-32\python.exe" -m mt5linux
# Ctrl+B then D to detach once it prints "server started on [...]:18812"

# 5. In the MT5 terminal itself (via the noVNC viewer), click "Algo
#    Trading" in the toolbar so it's ON (green) -- fresh accounts start
#    with it off, and order_send() gets rejected without it, even though
#    the API connection itself works fine.

# 6. Native Linux side: this repo's own dependencies inside the container
#    (no separate venv needed -- the container's own Python is already
#    isolated from the host):
docker cp /path/to/trading mt5:/config/trading
docker exec -u abc mt5 pip3 install --break-system-packages \
    -r /config/trading/bot/requirements.txt \
    -r /config/trading/backtest/data_pipeline/requirements.txt
MT5_PHASE1_LOGIN=... MT5_PHASE1_PASSWORD=... MT5_PHASE1_SERVER=MetaQuotes-Demo \
    docker exec -u abc -e MT5_PHASE1_LOGIN -e MT5_PHASE1_PASSWORD -e MT5_PHASE1_SERVER \
    -w /config/trading mt5 python3 -m bot.run_live --account-type prop_firm --phase phase1 \
    --instruments EURUSD,GBPUSD,USDJPY,XAUUSD --symbol-suffix "" \
    --bridge mt5linux --bridge-host 127.0.0.1 --bridge-port 18812
```

**Updating the code on the VPS later:** `docker cp` copies *into* an
existing directory rather than replacing it if the destination already
exists -- `docker cp .../bot mt5:/config/trading/bot` silently nests as
`/config/trading/bot/bot/...` instead of overwriting, leaving stale code
running with no error. Always `docker exec -u root mt5 rm -rf
/config/trading/bot` first, then `docker cp` fresh (needs `-u root`,
since the earlier `docker cp` leaves those files root-owned and the
non-root `abc` user can't delete them).

**Memory:** MT5's embedded WebView2 browser component (used for the
in-terminal Market/news panels, unrelated to actual trading) can eat
several GB on its own -- `docker exec -u root mt5 pkill -f
msedgewebview2` reclaims it; the core trading pipeline doesn't depend on
it. Check `docker stats --no-stream` before assuming you need more RAM.

### Running more than one account on the same VPS

Confirmed working: a second (or third) MT5 account only costs about
400MB (one `terminal64.exe` + one `mt5linux` server), not a whole
second container, as long as WebView2 is kept suppressed. Steps:

```bash
# Copy the terminal install (NOT the whole first account's state) to a
# new portable location, then strip the copied login/session state --
# `cp -r` copies Config/ and Bases/ too, which makes the copy silently
# auto-login as the FIRST account instead of showing a fresh signup wizard.
docker exec -u abc mt5 cp -r "/config/.wine/drive_c/Program Files/MetaTrader 5" \
    "/config/.wine/drive_c/MT5-Second"
docker exec -u abc mt5 rm -rf "/config/.wine/drive_c/MT5-Second/Config" \
    "/config/.wine/drive_c/MT5-Second/Bases"
docker exec -d -u abc -e DISPLAY=:1 mt5 wine "C:\MT5-Second\terminal64.exe" /portable
# Then via noVNC: "Select a company" -> MetaQuotes Ltd. -> "Open a demo
# account" (not "Login to an existing account" -- there's nothing saved
# to log into). Enable Algo Trading on this one too.

# A second bridge server, different port (mt5linux's Wine-side Python
# is one persistent process per port -- one process can only ever be
# attached to one terminal at a time):
tmux new -s bridge2
docker exec -u abc mt5 wine "C:\Program Files (x86)\Python39-32\python.exe" \
    -m mt5linux --port 18813
```

**Critical gotcha, confirmed live:** once a second terminal exists on the
same Wine prefix, `mt5.initialize()` called with **no path** stops being
reliable for either terminal -- it resolves to whatever terminal was most
recently made "default" system-wide (apparently keyed off the last
explicit `initialize(path=...)` call from *any* process on the prefix),
not necessarily the one that bridge/account is supposed to be talking to.
This actually happened: a test meant for the first (default) account
silently placed a real order on the second account instead, discovered
only because `account_info().login` was checked before trusting the
result. **Once more than one terminal exists on a VPS, pass
`--terminal-path` (`MT5_TERMINAL_PATH`) explicitly for every account, including the first/default one --
never rely on the no-path fallback again, and always print/check
`account_info().login` before trusting an order result.**

```bash
python -m bot.run_live --account-type prop_firm --phase phase1 \
    --bridge-port 18812 --terminal-path 'C:\Program Files\MetaTrader 5\terminal64.exe' ...
python -m bot.run_live --account-type prop_firm --phase phase1 \
    --bridge-port 18813 --terminal-path 'C:\MT5-Second\terminal64.exe' ...
```

## Testing

`bot/tests/` -- 95 tests, all runnable without any MT5 connection
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
