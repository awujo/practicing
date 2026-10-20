# Bishop "aggressive" bot: rebuild (handover)

Branch `claude-bishop-aggressive` (repo awujo/practicing). It starts with **only the teaching material** of the
Bishop course. Rebuild the bot from it the same way the Kevin King SLK bot was built on branch `claude-kevin-king`.
Keep this file up to date with every commit: what is built, how it maps to the course, and what is open.

## Source material (the only source of truth for the rules)

| Path | What |
|---|---|
| `knowledge-base/videos/video-01 .. video-18/` | the 18-video core course: `notes.md` (all), `transcript.txt` (01, 04, 13) |
| `knowledge-base/videos/bishop-*/transcript.txt`, `plug-and-play/` | 10 Bishop sessions: bias entries, building bias 1+2, daily routine, entries part 5, repeating system, trades breakdown 2+3, what next, plug and play |
| `knowledge-base/supplementary/*.md` | written notes per Bishop session, SL measurements, chart-example notes |
| `knowledge-base/supplementary/source/bishops_trade_chart_examples.pdf` | Bishop's 60-page chart-example PDF (the only visual source kept) |
| `knowledge-base/STRATEGY.md` | the consolidated rulebook written from all of the above (sections 1-9). A summary, not the source: check every rule against the transcripts/notes before coding it, quote them in code comments as `[T video-13@...]` / `[N b_entries_part5]` |
| `reference/OPEN_QUESTIONS.md`, `reference/PROJECT_HISTORY.md` | lessons from the first Bishop bot on `main` (MT5/VPS, conservative + aggressive styles): read them, do not copy its code |

The video **frames were left out on purpose (low quality)**: do not rely on frame screenshots.

## What to build: the AGGRESSIVE style

STRATEGY.md §5 "Entry style spectrum": **Aggressive** = enter directly once the key-level + imbalance setup is fully
formed, without waiting for inducement/confirmation, with a wider stop (~10-11 pips). Conservative (wait for the
lower-TF confirmation, e.g. H2 engulfing) is a later option/setting, not the default. Bias = the top-down storyline
process of §2 (weekly/daily bias, key levels A / V / open-close, liquidity IRL/ERL, sessions §8, management §6).

## Target architecture (same as the Kevin bot; port the infrastructure from `claude-kevin-king`)

- **GitHub Actions** (repo is public until 1 Nov for free minutes): hourly live job (cron + an external hourly
  tick through the Mini App server `/cron/tick`), backtest job, examples-replay job. Candles: IC Markets cTrader
  (Open API secrets already in the repo: CTRADER_*), Dukascopy fallback, cached in the Actions cache.
- **Aiven MySQL** (secret DATABASE_URL / DATABASE_PASSWORD / DATABASE_CA): use a **separate table prefix or schema**
  (e.g. `bishop_bias`, `bishop_entries`, `bishop_settings`) so the Kevin bot's tables are untouched.
- **Telegram**: alerts only to the owner (chat id 1410229777, secret TELEGRAM_BOT_TOKEN). Use a separate bot token
  if the owner provides one, otherwise prefix every message "BISHOP".
- **Telegram Mini App on Render** (FastAPI + static JS, owner-only initData check): bias cards, entries, paper
  results, settings form (every rule a setting with the course default). A new Render service for this branch.
- Paper trading first: entries are tracked on paper (TP/SL/R) before any broker order.

Files worth porting from `claude-kevin-king` (adapt, don't copy blindly): `slk/candles.py`, `slk/store.py`,
`slk/ctrader*.py`, `slk/db.py`, `slk/settings.py`, `slk/live.py` (run loop, reconcile, alerts, Telegram),
`webapp/` (auth, API, Mini App), `.github/workflows/{live,backtest,verify-examples,backfill}.yml`, the tests style.

## Working rules (from the owner)

- Follow the teaching exactly; validate every rule against the transcripts/notes; say when something is our choice.
- Backtest every rule choice (all pairs, 2018+, costs included) and report honestly; no curve fitting.
- Telegram messages in readable sections (headline / key level / story so far / context / plan).
- Never print or commit secrets; the owner must not paste secrets in chat (GitHub Secrets / Render only).
- Commit + push to this branch only; no PRs unless asked; update this HANDOVER.md each commit.

## Status

- 2026-10-20: branch created with the material only (no code yet).
