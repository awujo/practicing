# Brief for Qwen: Kevin King SLK-style bot

Read this whole file first. The owner is cost-sensitive: keep every reply and
every file short, commit small, never build ahead of the stage you are on.

## Goal
A bot that follows Kevin King's SLK-style method and does 3 things:
1. **Bias**: say what each pair's bias is (weekly -> daily -> 4H -> lower TF) and why.
2. **Entry alert**: send a Telegram alert when an entry setup completes.
3. **Place the trade** on IC Markets via the cTrader Open API (demo first).

## Source of truth: the knowledge base ONLY
- Transcripts: `knowledge-base/videos/kevin-*/transcript.txt` (29 videos, timestamped).
- Chart frames: `knowledge-base/frames/kevin-*/` (sheets + index, 1280px tiles).
- Do NOT use any old bot/engine code from other branches. Start from zero.
- Every rule you write must cite its source (video slug + timestamp). Mark anything
  you are guessing as `UNCONFIRMED` and ask the owner. Never invent rules.

## Architecture (fixed by the owner)
| Part | Choice |
|---|---|
| Broker / data / execution | IC Markets, cTrader Open API (protobuf; demo host demo.ctraderapi.com, live host live.ctraderapi.com, port 5035) |
| Runner | GitHub Actions only. No VPS, no Docker, no MT5 |
| Database | Aiven MySQL (SSL required) |
| Interface | Telegram Mini App (Web App) served by a Render web service |
| Config / secrets | Render env vars for the web app; GitHub Actions Secrets for the runner |

Hard facts to design around:
- GitHub `cron` is best effort. In practice an "hourly" job fired every 4-8 hours.
  Do not rely on it for timing. Use a long-running job (checks every minute for ~5.5h,
  then hands over to the next run) started by `workflow_dispatch` from an external
  timer, and measure the real delay in Stage 1.
- Render cannot hand its env vars to GitHub Actions. The runner needs its own
  GitHub Secrets. Keep these minimal: DB URL, Telegram bot token, an encryption key.
  Everything else (cTrader tokens, risk settings, pair list, kill switch) lives in the
  DB, encrypted where sensitive.
- Render free sleeps after ~15 min idle: fine, because state is in Aiven.
- cTrader Open API needs a persistent connection and a heartbeat about every 10s,
  and OAuth access tokens expire (use the refresh token and store the new one in the DB).
- NEVER commit a secret, a token, a password or a connection string. Never print
  secrets in logs. If you see one in a file or chat, tell the owner to rotate it.

## Stages. Stop at the end of each stage and wait for the owner's "go".
**Stage 0 - Understand (no code).** Read the transcripts and frames. Write
`STRATEGY.md`: the method in plain rules (bias, key levels, liquidity, structure,
entry confirmation, stop, target, when NOT to trade), each with a source citation, plus a
list of open questions. Keep it under ~300 lines.

**Stage 1 - Skeleton and timing.** Aiven schema (pairs, candles, bias, signals, trades,
settings, runs), a GitHub Action that runs, writes a row, sends one Telegram message, and
logs how late it started. Report the real run time, minutes used, and start delay.

**Stage 2 - Data.** Pull candles (W, D, H4, H1, M15) from cTrader into the DB for
a few pairs, incrementally. Check the data is complete and fresh.

**Stage 3 - Bias + entry alerts (notify only).** Implement STRATEGY.md as small,
testable functions with no look-ahead. Backtest on stored candles and show the owner a
handful of trades next to the frames from the videos. Alerts go to Telegram. Nothing trades.

**Stage 4 - Telegram Mini App.** Render web service: bias board, recent alerts, trade
list, settings, kill switch. Validate Telegram `initData` (HMAC with the bot token) on every
request and allow only the owner's Telegram user id.

**Stage 5 - Trading, demo account only.** Pending/market order with stop loss and take
profit attached at the broker, so the broker holds the risk even if the runner dies.
Guardrails: demo only until the owner says otherwise; risk per trade % and max open
trades from DB settings; one order per signal id (idempotent); kill switch checked
before every order; a Telegram confirm button before any order unless auto mode is enabled.
Going live is a separate decision by the owner, never your default.

## Working rules
- One branch: `qwen-kevin-king`. Small commits. No PRs unless asked.
- Short replies. Show results (numbers, a link, a screenshot), not plans.
- Keep a `HANDOVER.md` (10 lines max) updated: what is done, what is next, open questions.
- If a step could cost money, trade, or expose a secret, ask first.
