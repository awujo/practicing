# HANDOVER.md

Done: Stage 0 (STRATEGY.md). Stage 1 skeleton: schema.sql applied LIVE to Aiven (7 tables,
MySQL 8.4.11 verified), stage1/run.py + workflow `stage1-runner.yml` committed.
Bot @SLK_KKbot token works (getMe OK). Owner pasted DB password + bot token in chat ->
ROTATE BOTH before going live; never commit them.
Next: owner (1) DMs @SLK_KKbot "/start" so the chat id is readable via getUpdates,
(2) adds GitHub Secrets DB_URL / TG_BOT_TOKEN / TG_CHAT_ID, (3) runs the workflow with
planned_at set -> reports real start delay + minutes used. One Telegram message = Stage 1 done.
Still open: STRATEGY.md Q1-Q5 (risk %, sessions, pairs, min RR, scoring weights).
Blocked later: cTrader Open API app approval, Render service (SETUP_GUIDE.md).
Reminder: GitHub cron drifts 4-8h -> long-running job pattern is built into run.py (--minutes).
## Relay update (owner side, 2026-10-11) — READ THIS FIRST
1. **Push gap:** this environment has no GitHub credentials, so commits here never reached
   awujo/trading. Owner relayed: push everything to branch `qwen-kevin-king`. Until a push
   mechanism exists (PAT in env, or owner pulls via bundle), the owner-side copy is stale.
   A git bundle of Stage 0+1 was prepared at commit 6a0b11e for manual transfer.
2. **Bot token REVOKED/invalid:** getMe now returns 401 Unauthorized with the token from chat.
   It worked earlier today -> it was revoked (likely by the recommended rotate). Owner must
   create/revoke via BotFather and put the NEW token in repo secret TG_BOT_TOKEN.
3. **Chat id still unknown:** with a valid token, DM @SLK_KKbot /start, then run getUpdates —
   code fetches it automatically (see stage1/run.py fallback) or read it manually.
4. **Q1-Q5 answered as defaults** (relay): risk 0.5%/max2, sessions LDN+NY, minRR 2.0,
   pairs = CADJPY EURGBP AUDCAD NZDJPY GBPUSD + transcript examples (8 total), scoring
   weights proposed by Qwen (STRATEGY.md table). All marked UNCONFIRMED, tunable in `settings`
   (rows already inserted into Aiven: pairs, w_bias..w_session, score_threshold_strong/weak).
5. **Workflow hardened:** planned_at input left empty now auto-defaults to dispatch time
   instead of crashing argparse.

## Owner FINAL answers to Q1-Q5 (2026-10-11, relayed) — supersedes item 4 above
- Sessions: NO restriction, trade any session; session stored as a field on every signal/trade
  for per-session backtest comparison. settings.sessions=ALL, session_filter=off.
- Pairs: NO restriction; target = ALL IC Markets cTrader pairs (Stage 2 symbol sync once API
  app approved). Start set = majors + video pairs (8 in `pairs` table). pair_filter=off.
- Risk 0.5% / min RR 2.0 kept as EDITABLE SETTINGS (backtest may sweep them), not rules.
- Scoring weights: Qwen-proposed with transcript citations (STRATEGY.md); w_session is a score
  bonus only, never a filter.
- Backtest protocol: every pair × every session, report per-pair AND per-session, no
  pre-filtering, and WALK-FORWARD SPLIT (tune on older ~70%, validate untouched on newer ~30%)
  to reject luck-based rules. Recorded in STRATEGY.md.
- LIVE DB updated accordingly: columns signals.session, trades.session, trades.pnl_rr added +
  idx_trades_session created; settings upserted (verified by SELECT dump). schema.sql/run.py
  updated so fresh installs get the same state (run.py has idempotent migrate()).
- qwen-stage1.bundle refreshed at this commit — owner: `git pull ./qwen-stage1.bundle qwen-kevin-king && git push origin qwen-kevin-king`.

