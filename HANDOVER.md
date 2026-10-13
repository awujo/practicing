# HANDOVER — read this first in a new chat

Project: Kevin King "SLK" trading bot. Gives **bias** (main goal), then **entry alerts**, later **trades on
IC Markets cTrader (demo first)**. No VPS, no Docker, no MT5.

Repo `awujo/trading`, work branch **`claude-kevin-king`** (Claude). `qwen-kevin-king` = Qwen's older attempt,
ignore. `main` = old bot code, don't touch. Owner Telegram chat id: 1410229777.

**Rule for every session:** update this file (Status + Log) in the same commit as any change.

## Architecture
| Part | Where | Runs on |
|---|---|---|
| Strategy (the rules) | `STRATEGY.md` (v0.3) | — |
| Course evidence | `knowledge-base/` (transcripts, frame sheets), `knowledge-base/study/*.md` notes | — |
| Bias engine | `slk/structure.py`, `levels.py`, `story.py`, `candles.py`, `data.py` | — |
| Bias backtest | `slk/backtest.py` → `reports/REPORT.md` | GitHub Actions `backtest.yml` (on push to slk/**) |
| Entry model + backtest | `slk/entry.py`, `slk/entry_backtest.py` → `reports/ENTRY_REPORT.md` | same workflow |
| Live bias runner | `slk/live.py`, `slk/db.py`, `db/schema.sql` | Actions `live.yml`, hourly at :07 |
| cTrader client | `ctrader/` (README has OAuth steps) | Actions `ctrader-smoke.yml` |
| Telegram Mini App | `webapp/` (FastAPI), `render.yaml` | Render, branch claude-kevin-king, root `webapp` |
| Shared names (env vars, DB tables) | `CONTRACT.md` | — |
| Code review findings | `REVIEW.md` | — |

Data: Dukascopy free hourly candles (works from Actions; blocked from Claude's sandbox). cTrader candles later.
Candles close 17:00 New York. Secrets: `DATABASE_URL`, `TELEGRAM_BOT_TOKEN` (chat id defaults to owner).
Claude cannot read Actions logs (redirect blocked) → workflows write errors as `::error` annotations or into
`reports/run.log`, which Claude reads via the GitHub API.

## Status (2026-10-13)
- [x] Strategy studied: all 29 transcripts + all ~700 frame sheets. STRATEGY.md v0.3.
- [x] Bias engine, entry model, live runner, cTrader client, Mini App — all built, tests pass (`pytest -q tests`).
- [ ] **Backtest results on real data** — run in progress (28 pairs, 2018–2025). Read `reports/REPORT.md` when committed.
- [ ] **Live runner** — fails: Aiven `Access denied` → user must fix the password in GitHub secret `DATABASE_URL`.
- [x] Code review done (`REVIEW.md`): 9 fixed (incl. look-ahead in story backtest, HTF filter now applied), 30 open.
- [ ] **Default branch must be `claude-kevin-king`** (now `qwen-kevin-king`) or the hourly live job never runs (GitHub runs cron only on the default branch). User: Settings → General → Default branch.
- [ ] Render deploy of Mini App (user: set branch + root dir + 2 env vars).
- [ ] cTrader: app "SLK" id 43716 is *Submitted* (not active). Get tokens per `ctrader/README.md`, then run cTrader smoke workflow.
- [ ] Top open review items: swing rule (fractal vs close-beyond), M/W conflict not enforced, alternative story start, entries not wired into live runner.
- [ ] Ideas not built: Mini App page to paste cTrader tokens into DB; alerts for entries (`entries` table) in live runner;
      HTF-agreement filter in live runner; "sweep previous day high/low" alternative story start.

## Next steps (in order)
1. Fix `DATABASE_URL` → rerun "SLK live bias" (Actions → Run workflow, or Claude dispatches it via API).
2. Read backtest reports; tune `slk/story.py` DEFAULT / entry DEFAULT by results (out-of-sample years).
3. Deploy Mini App on Render, set BotFather menu button to the Render URL.
4. Entry alerts live → then demo trading with kill switch + confirm button.

## Log
- 2026-10-12/13: Kevin King course study (transcripts + frames), STRATEGY v0.1→v0.3.
- 2026-10-13: Built engine + backtest; parallel agents built entry model, live runner, cTrader client, Mini App.
  Fixed CI deps (`requirements-dev.txt`). Chat id default set. Live run blocked by Aiven password.
  User DB = `Claude-KK-SLK` (Qwen uses defaultdb). Review agent fixed 9 issues; old backtest reports invalid (look-ahead), rerun.
