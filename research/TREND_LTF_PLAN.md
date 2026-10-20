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

### 28-pair results (Actions run 39412272945, 2018-2025, train < 2023 <= test; reports/TREND_REPORT.md,
### reports/LTF_DISCOVERY.md, reports/pattern_trades.csv.gz with 105,442 rows)
1. Blind limit at Kevin's line: H1 -0.29 .. -0.58 R, H2 -0.21 .. -0.43 R, H4 -0.18 .. -0.35 R per trade
   (1R..5R targets). Same in train and test.
2. H1-close confirmation entry: -0.08 .. -0.16 R on every TF, train and test. Clearly better than the limit, the
   most stable finding of this study, but still negative after the 1.2-pip cost.
3. Trend filters do not help: D+W trend agree -0.13 R, D/H4 in line -0.15 R, against the D trend -0.12 R
   (confirmation entries, 3R target). Kevin's "with the trend" adds nothing on these mechanical levels.
4. The impulsive-breakout-candle lead from the 8-pair run did NOT hold on 28 pairs.
5. Discovery: 1 single condition held (dow=6 = entries closing on Sunday, n 152: market-open gaps, ignore);
   11 two-condition rules held, all "session=late" + a wider stop on limit entries. By hour: the whole effect is
   entries at 21-22 UTC (+0.43 / +0.35 R at 3R; every other hour negative) = the daily rollover, when spreads
   widen and BID candles spike. Almost certainly an artefact of bid-only candles + a flat cost; needs ask-side
   data or a rollover spread model before anyone believes it. Shuffled chance level is ~0 for these, but a
   shuffle also removes this mechanical effect, so that does not make it real.
6. Verifier agent (independent, 2026-10-20): no look-ahead (truncation test on 51 rows), 128 trades recomputed by
   hand all match. Fixed after its report: h1_confirm stops capped at 25 pips, "holds" needs the full MIN_LIFT on
   test, chance-level shuffles in the report, caveats in slk/ltf_discovery.py. Not fixed (noted): rows overlap
   (~half within 24 h of another same-pair same-side row), _TF lacks the forming-last-bar guard (matters only
   live), R_target picks the last H4 story in list order.

### Next steps (for whoever continues)
- Conclusion so far: no mechanical lower-TF edge after costs. The confirmation entry is the one improvement
  worth keeping in mind for the live entry alerts (owner decides).
- To test the rollover lead: drop hours 20-23 UTC, or add a per-hour spread (IC Markets ask-bid) before trusting it.
- De-duplicate overlapping rows (one trade per pair/side at a time) before any significance claim.
- Ideas not built: overlap of the entry line with a fresh D/H4 level (cue 14), tap count before the break
  (cue 13), engulfing at the reaction (cue 11), choosing the entry TF with the best RR (cue 21), TP1 at the H1
  swing + TP2 at the next H4 level (cue 22), a real per-hour spread model (rollover).
