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
