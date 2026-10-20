# cTrader Open API client (IC Markets)

Synchronous client for short-lived jobs (GitHub Actions): TLS socket to `demo.ctraderapi.com:5035`
(or `live.ctraderapi.com:5035`), 4-byte big-endian length + `ProtoMessage`, heartbeat every 10 s.
The protobuf classes are Spotware's generated `*_pb2.py` from the `ctrader-open-api` package
(v0.9.2, MIT), vendored in `ctrader/messages/`. The package itself is not used: it is a Twisted
reactor client and pins old protobuf/requests versions. Dependencies: `protobuf>=3.20`, `pandas`, `requests`.

| File | What |
|---|---|
| `client.py` | `CTraderClient`: `app_auth`, `account_auth`, `get_trader`, `get_symbols`, `get_trendbars`, `trendbar_rows`, `get_spot`, `get_positions`, `get_orders`, `place_market_order`, `place_limit_order`, `amend_position_sltp`, `close_position`, `cancel_order` |
| `tokens.py` | `refresh_tokens()`, token storage in DB `settings`, one-time OAuth CLI |
| `sizing.py` | `volume_for_risk`, `pip_value_per_lot`, `client_order_id(entry_id)` |
| `smoke.py` | `python -m ctrader.smoke [--test-order]` |
| `framing.py` | encoding and decoding of frames |

```python
from ctrader import CTraderClient, client_order_id, volume_for_risk, pip_value_per_lot
with CTraderClient() as c:                       # connect + app auth + account auth (+ token refresh)
    bal = c.get_trader()["balance"]
    s = c.symbol("EURUSD")
    vol = volume_for_risk(bal, 0.5, stop_pips=20, pip_value_lot=pip_value_per_lot(s["pip_position"], s["lot_size"]),
                          lot_size=s["lot_size"], min_volume=s["min_volume"], step_volume=s["step_volume"],
                          max_volume=s["max_volume"], max_lots=2)
    if vol:
        c.place_limit_order("EURUSD", "BUY", vol, price=1.0850, stop_loss=1.0830, take_profit=1.0890,
                            client_order_id=client_order_id(entry_id), label="SLK")
```

Notes:
- **Volume** is in cents of units: `100000` = 1,000 units = 0.01 lot on FX (FX `lotSize` = `10000000`).
- **Market orders** accept only relative SL/TP. The client derives them from the current ask/bid (or `ref_price`),
  then amends the position to the exact absolute SL/TP after the fill. Limit orders send absolute SL/TP.
- **Idempotency**: `client_order_id(entry_id)` -> `slk-e<id>`. It is sent as `clientOrderId` and `comment`. Before
  sending, open positions and pending orders are checked for it, and a match returns `{"status": "DUPLICATE", ...}`.
  The caller should also record it in `orders.client_order_id` (UNIQUE).
- **Safety**: new orders raise `TradingRefused` when settings `kill_switch` is `on`, or when `CTRADER_ENV` is not `demo`
  or the account is live, unless `allow_live=True` is passed. Closing a position or cancelling an order is still
  allowed while the kill switch is on. When `DATABASE_URL` is set and `slk/db.py` cannot be used, the client raises
  an error and does not trade, so the kill switch is never skipped.
- **Trendbars**: `get_trendbars(symbol, "H1", start, end)` returns the same frame as `slk.data.hourly`: UTC index `t`,
  columns `open, high, low, close`, bid prices. `trendbar_rows(symbol, period, start, end)` returns rows
  `(t, open, high, low, close, volume)`. Each request covers the largest window the API accepts (`_CHUNK`: M1-M5
  5 weeks, M10-H1 35 weeks, H4-D1 1 year, W1/MN1 5 years; a window the server refuses with `INCORRECT_BOUNDARIES` is
  halved). A reply that leaves a hole of more than 4 days at either end of its window (a server-side bar cap) is
  completed by more requests. History requests are spaced `HIST_MIN_GAP_S` = 0.25 s apart (Spotware allows 5 per
  second per connection) and retried with backoff on `REQUEST_FREQUENCY_EXCEEDED`.
- **Candle source of the bot**: `slk/store.py` uses this client as the PRIMARY H1 source for the candle store (live,
  backfill, backtest, verify-examples), ONE connection per job for all pairs (`store.get_feed()`); IC H1 bars are
  hour-aligned UTC bid bars, zero-volume and FX-weekend bars are dropped, so the 17:00 New York D/W/M candles
  (`slk/candles.py`) are built exactly as from Dukascopy, which remains the fallback. Those workflows need the same
  `CTRADER_*` secrets as the smoke test, plus `DATABASE_URL` / `DATABASE_PASSWORD` / `DATABASE_CA`, so a token
  refreshed by one job is stored in the DB for the next one. Errors are logged without tokens or account numbers.
- **Tokens**: the client reads `ctrader_access_token`, `ctrader_refresh_token` and `ctrader_token_expiry` (unix
  seconds) from DB `settings`, and falls back to the env secrets. It refreshes the token when less than 3 days are
  left, or once when account auth fails with a token error, and stores the new pair in the DB. A refresh invalidates
  the old refresh token. **Once the DB holds tokens, the DB is the source of truth**, and the GitHub secret becomes
  stale. That is fine, because the DB values are used first.
- `CTRADER_ACCOUNT_ID` can be either the ctidTraderAccountId or the account login number shown in cTrader.
  The client resolves it with `ProtoOAGetAccountListByAccessTokenReq`. If the token sees only one account, you
  can leave it unset.

## One-time setup: getting the tokens for app 43716 ("SLK")

1. In https://openapi.ctrader.com/apps, open the app and add a **redirect URI**. Any URL you control works,
   for example `https://<your-render-app>.onrender.com/ctrader/callback`. A URL that returns 404 also works,
   because you only need the `code` parameter from the address bar. Copy the **Client ID** and **Secret**.
2. Build the authorization URL (scope `trading`):
   ```
   CTRADER_CLIENT_ID=43716_xxx python -m ctrader.tokens auth-url --redirect-uri https://YOUR/callback
   # -> https://openapi.ctrader.com/apps/auth?client_id=...&redirect_uri=...&scope=trading
   ```
   Open it, log in with the **cTrader ID that holds the IC Markets demo account**, and grant access to that account.
3. The browser goes to `https://YOUR/callback?code=XXXX`. Exchange the code within about a minute:
   ```
   CTRADER_CLIENT_ID=... CTRADER_CLIENT_SECRET=... \
     python -m ctrader.tokens exchange --code XXXX --redirect-uri https://YOUR/callback   # add --save-db to store in DB
   ```
   This prints `accessToken`, `refreshToken` and `expiresIn` (about 30 days). Run it on your own machine, not in CI.
4. Add the GitHub repository secrets (Settings -> Secrets and variables -> Actions):

| Secret | Value |
|---|---|
| `CTRADER_CLIENT_ID` | app Client ID |
| `CTRADER_CLIENT_SECRET` | app Secret |
| `CTRADER_ACCESS_TOKEN` | `accessToken` from step 3 |
| `CTRADER_REFRESH_TOKEN` | `refreshToken` from step 3 |
| `CTRADER_ACCOUNT_ID` | IC Markets demo account number (login) or ctidTraderAccountId |
| `CTRADER_ENV` | optional; workflows use `demo` |
| `DATABASE_URL` | optional for the smoke test; needed for the kill switch and for persisting refreshed tokens |

5. Run **Actions -> cTrader smoke -> Run workflow**. Tick `test_order` to open and close one 0.01-lot EURUSD demo
   position with SL/TP. When the secrets are missing, the workflow prints a message and exits 0.

**App status:** while app 43716 shows **"Submitted"** rather than **"Active"** on the Open API portal,
Spotware may refuse the OAuth flow or the `ProtoOAApplicationAuthReq` (for example with
`CH_CLIENT_AUTH_FAILURE`). The smoke test prints this hint. Wait for approval, then retry. Nothing in the code
needs to change.
