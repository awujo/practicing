# Trend entries, Kevin gap, lower-TF discovery (plan + status)

Owner request 2026-10-20. Written first so another coding agent (ChatGPT / Codex / a new Claude chat) can
continue from here. Branch `claude-kevin-king`. Update the Status lines below with every commit.

## Why
Every bias backtest (reports/REPORT.md, reports/LEG_REPORT.md, research/results/*) is slightly negative after
costs. Replaying Kevin's 6 dated trades (tests/kevin_trades.json, reports/KEVIN_TRADES.md) shows the bot misses
all 6. Kevin mostly trades WITH the W/D trend on H4/H2/H1 key levels, with 7-19 pip stops, often after the
Daily story already reached its target or with no Daily story at all. Our engine only builds M/W/D stories, so
lower-TF setups are invisible.

## Study 1: trend entries (`slk/trend_study.py`)
- New story TF `H4` (origin H4 key-level tap-reject-close, confirm = H1 body close beyond point B), same rules as
  the D story (slk/story.py `STORIES["H4"] = ("H4", "H1")`).
- Keep only H4 stories whose side agrees with the D trend (variants: no filter / D / D+W) at the confirmation.
  The Daily story's target being hit already does NOT block the trade.
- Entry = the H1 confirmation close. Stops: tap wick + 2 pips (Kevin "cover the level"), min 7 pips.
  Targets: story target (H4 ERL), fixed 2R, 3R. Walk on H1, stop first on a shared candle, 1.2 pip cost,
  max 5 days. Also MFE (best R before the stop) for Study 3.
- Report: reports/TREND_REPORT.md (+ trend_trades.csv). Train 2018-2022 / test 2023-2025 on the Actions data.

## Study 2: why the bot does not see Kevin's trades (`slk/kevin_gap.py`)
For each trade in tests/kevin_trades.json: is there a D/W story on his side at his time? an H4 story (level near
his stop, confirmation within 3 days)? If not, re-run with one filter off at a time (trend_filter, htf_filter,
next_day_rule, target_unswept, fresh levels ...) and name the filter that blocks it. Report reports/KEVIN_GAP.md.

## Study 3: lower-TF confirmation discovery (`slk/ltf_discovery.py`)
Question: at an entry, is there something on the lower TF (H1 inside H4; M15/M5 later) that raises the chance
of the trade working or of a bigger fixed reward?
- Features measured ONLY from candles closed at the entry time (no look-ahead): list in the module docstring
  (H1 sweep of the previous H1 swing before the break, break-candle size vs ATR, imbalance/FVG left by the
  break, H1 structure, distance from the level, hour/session, number of earlier touches, stop size, D/W trend).
  Feature ideas come from Kevin's transcripts (knowledge-base/), extracted by a separate study agent.
- Outcomes: hit +1R / +2R / +3R before -1R, MFE in R.
- Method: decide on the TRAIN years only (pre-declared feature buckets, min 100 trades per bucket), then check
  the chosen rules once on the TEST years. Report what holds and what does not. No ANN; nothing goes live
  without the owner.
- Independent verifier agent: audits the code for look-ahead and recomputes a sample of trades by hand.

## Data limits
Local sandbox: 8 pairs H1 2022-2026 in data/examples (development only). Full runs: GitHub Actions
backtest.yml (28 pairs, cTrader cache). Only H1 candles are stored. Kevin: "90 percent of my
entries are from four hours or two hours", M15/M5 not used (research/KEVIN_LTF_CUES.md #2), so H1 is enough.

## Status
- 2026-10-20: plan written; Studies 1-3 built and run on the 8 local pairs (2022-2026, train < 2025 <= test).
  Reports: reports/trend_local/TREND_REPORT.md, LTF_DISCOVERY.md, reports/KEVIN_GAP.md. Kevin's cues:
  research/KEVIN_LTF_CUES.md. Full 28-pair run (2018-2025, train < 2023 <= test): backtest.yml step "Trend
  entries + lower-TF discovery" -> reports/TREND_REPORT.md, LTF_DISCOVERY.md, pattern_trades.csv.gz.

### Results so far (8 pairs, local; cost 1.2 pips; nothing live)
1. H4 stories (tap wick stop, entry at the H1 confirmation close): median stop 43 pips (Kevin: 7-19), every
   filter -0.03 .. -0.2 R per trade. Not Kevin's trade.
2. Kevin continuation levels on H4/H2/H1, limit at the line, Kevin's stop (median 6.6 / 8.5 / 10.3 pips): -0.2 ..
   -0.6 R. Cause: 35-42 % are stopped IN THE FILL HOUR (H1 ATR ~14 pips > the stop). That is a real loss
   (price touches the line first, then the stop), not an H1 artefact.
3. Same levels, entry = close of the first H1 candle that closes back on our side after the touch (stop never
   touched): -0.08 .. -0.17 R (train and test). Much better than the blind limit, still below zero.
4. Discovery (446 single conditions, train-chosen): 5 held on test, about the chance level for that many tests.
   Recurring theme: an impulsive breakout candle (break_body_atr > ~0.8, bo_body_x_avg > ~2.4) on H2/H4
   h1_confirm entries = Kevin's "volume candle" (cue 10). Also "late session" (17-24 UTC) and wider stops, which
   may just be cost effects (flat 1.2 pip cost; real rollover spreads are wider) -> treat with suspicion.
5. Kevin gap: of his 6 trades, the D story was already at its target (3) or on the other side (2) at his time;
   only 1 had an active same-side D story. The bot only alerts M/W/D stories, so it cannot show these. H4
   stories exist within 6-10 pips of his entry for EURAUD 17 Feb, EURGBP 2 Feb, USDJPY 12 Dec.

### Next steps (for whoever continues)
- Read the 28-pair reports when the Actions run has committed them. A condition counts only if it holds on the
  28-pair TEST years too; then add it as an entry setting (off by default) and paper-track it live first.
- Cross-check agent findings: see the HANDOVER log entry of 2026-10-20 (look-ahead audit).
- Ideas not built: overlap of the entry line with a fresh D/H4 level (cue 14), tap count before the break
  (cue 13), engulfing at the reaction (cue 11), choosing the entry TF with the best RR (cue 21), TP1 at the H1
  swing + TP2 at the next H4 level (cue 22), a real per-hour spread model (rollover).
