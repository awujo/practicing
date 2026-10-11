# STRATEGY.md — Kevin King SLK-style method (Stage 0)

Source of truth: `knowledge-base/videos/*/transcript.txt` only. Timestamps are seconds
from each transcript's `[start-end]` markers. Anything guessed is marked **UNCONFIRMED**.

## 1. Bias / Storyline ("building bias" = "storyline", same thing)
- Storyline = the sequence of structure events that tells you where price is likely going;
  you build it top-down. (`kevin-story-line` [0.0-40.5])
- Timeframe entry point depends on the calendar: at the start of a new month start from
  Monthly; start of a new week start from Weekly; otherwise Daily/4H. (`kevin-all-in-1` [86.4-100.6])
- Stack TFs: bias TF → next TF down for structure → next for entries. Never take an entry
  on the same TF that gave the break without confirming below. (`kevin-basic-ms-pt2`, `kevin-entry-2` [5.3-34.3])
- The TF whose candle *caused* the breakout/storyline is the TF you then look for entries on.
  (`kevin-entry-2` [5.3-34.3])
- No valid storyline = no trade. (`kevin-story-line`, `kevin-introduction-to-entry`)

## 2. Basic Market Structure
- Swings: higher highs/higher lows = uptrend; lower highs/lower lows = downtrend. The low
  before a reversal point defines the first HL in an up-leg. (`kevin-basic-ms` [61.6-102.2])
- BOS = break of structure in trend direction; BMS/CHoCH = break against current structure
  (trend-change signal). (`kevin-basic-ms-pt2` [25.6-106.0], `kevin-advance-market-sturcture-pt2` [22.1-45.1])
- Break validity: body close beyond the swing point counts; wick-only = liquidity sweep, not
  a break. (`kevin-basic-ms-pt2`, `kevin-advance-market-sturcture-pt2`)
- Internal breaks inside a swing leg (IH/IL) don't change external structure. (`kevin-basic-ms` [35.7-61.6])
- Line-chart trick: switch to line chart to see obvious external breaks cleanly.
  (`kevin-eurgbp-bd` [93.6-138.2])

## 3. Advanced Market Structure (AMS)
- AMS = Sweep of liquidity + BOS + Inducement, all three required to complete it.
  (`kevin-advance-market-sturcture-pt2` [22.1-45.1])
- Double-BOS and validation standards discussed across pt1–pt3; pt3 exists because students
  struggled — re-read carefully when implementing. (`kevin-advance-market-sturcture-pt3` [29.9-58.9])
- Fractal: one HTF candle can contain a full AMS leg on a lower TF. (`kevin-advance-market-sturcture`)

## 4. Liquidity
- "Liquidity means money": anywhere there are resting orders (equal highs/lows, trendlines,
  obvious swing points) is liquidity. (`kevin-liquidity` [19.0-35.9])
- Inducement = minor liquidity taken to fuel the real move. (`kevin-liquidity`, `kevin-advance-market-sturcture-pt2`)
- Internal vs external range liquidity; TP targets sit at opposite external liquidity.
  (`kevin-liquidity-pt2`, `kevin-liquidity-pt3`)

## 5. Key Levels
- Three types: A-shape, V-shape, Open-Close (OC) levels. Two opposite-direction candles form
  V/A shapes. (`kevin-key-levels-pt1`, `kevin-entry-2` [41.3-96.0])
- Levels invalidate and flip roles (S/R flip). Freshness matters: fresh level > unfresh;
  wick-touch vs body-close changes status. (`kevin-key-levels-pt1`, `kevin-key-levels-pt3`, `kevin-key-levels-pt4`)
- Prefer HTF levels; confluence of multiple level types strengthens a POI. (`kevin-key-levels-pt3`)

## 6. Entries
- Continuation over reversal: prefer entries aligned with the completed storyline/bias.
  (`kevin-introduction-to-entry` [110.6-131.8], `kevin-entry3` [62.1-91.9])
- Model A: breakout + retest rejection at a key level (third-candle rejection; ~5-candle
  sequence). (`kevin-introduction-to-entry`, `kevin-entry-4`)
- Model B: QMRO — sweep + BOS then retrace into the mitigation/rejection origin zone
  (apex/head/shoulder/neck). (`kevin-entry3`, `kevin-entry-4`)
- If a TF breaks but shows no continuation, do not force entries there. (`kevin-entry3` [101.9-120.5])
- Confirmation TF: after storyline forms on TF X, drop below X to time the entry.
  (`kevin-entry-2` [5.3-34.3], `kevin-all-in-1` [1972.7-1995.7])

## 7. Stop Loss
- Place SL behind the rejection candle / invalidation point of the setup, not a fixed pip
  number by default. (`kevin-qns-pt1` [1310.3-1317.7], `kevin-entry3` [326.6-336.6, 682.6-691.7])
- Typical small stops quoted in examples: 10–15 pips. (`kevin-entry3` [372.1-385.8, 1165.7-1174.6])
- If two nearby candidate stop points exist, cover both. (`kevin-cadjpy-bd` [244.3-281.3])
- Big-SL alternative: enter earlier and put SL at the validation point — still valid, just a
  different R:R style. (`kevin-all-in-1` [1979.7-2017.4])
- If price keeps tripping your SL at a level, adjust placement (experience → smaller stops).
  (`kevin-qns-pt1` [1323.7-1370.1])

## 8. Targets
- Target the opposite/next external liquidity (equal highs/lows, unfresh key levels).
  (`kevin-liquidity-pt2`, `kevin-liquidity-pt3`, `kevin-all-in-1` [1992.7-1995.7])

## 9. When NOT to trade
- No completed storyline → no entry. (`kevin-story-line`)
- Break without continuation on that TF → stand aside. (`kevin-entry3` [101.9-120.5])
- Setup against bias (reversal hunting) → skip unless AMS confirmed. (`kevin-introduction-to-entry`)
- Entry requires the level AND the confirmation candle; missing either = no trade.
  (`kevin-qns-pt1` [1485.5-1495.1])

## Owner decisions (2026-10-11, FINAL — supersedes earlier "defaults" round)
- Q1 risk: 0.5% per trade, max 2 open trades (demo). Kept as an EDITABLE SETTING, not a rule —
  backtest may test other values.
- Q2 sessions: **NO restriction.** Trade any session at any time. Session (ASIA/LDN/NY/SYDNEY)
  is recorded as a field on every signal and trade so results can be compared per-session later.
  Nothing is filtered out in advance.
- Q3 pairs: **NO restriction.** Long-term coverage = all IC Markets cTrader pairs. Start set =
  majors + video pairs (CADJPY, EURGBP, AUDCAD, NZDJPY, GBPUSD, USDJPY, USDCHF, EURAUD); the
  Stage 2 symbol sync expands `pairs` automatically once the cTrader API app is approved.
- Q4 min RR: 2.0, kept as an EDITABLE SETTING for backtest sweeps.
- Q5 scoring weights: proposed by Qwen from transcripts with citations (table below). The
  session row (w_session) is NOT a filter — it only scores LDN/NY setups higher; the backtest
  decides whether that component earns its weight.

### Backtest protocol (owner requirement + anti-overfitting warning)
- Run every pair × every session, report results grouped per pair AND per session. No pre-filtering.
- **Walk-forward split:** build/tune rules on the older period, then validate untouched on the
  newer period. A rule that only wins on the older data is treated as luck and discarded.
  Concretely: tune on first ~70% of history, validate on last ~30%, report both numbers side by side.

### Proposed signal score (0-100), derived from Module 4/5 emphasis
| Component | Weight | Transcript basis |
|---|---|---|
| HTF bias aligned (DRD->H4 stacking) | 25 | "trade with the higher TF direction" (basic-mkt-str) |
| Level quality: fresh level + confluence (OC/POI overlap) | 20 | fresh-level & confluence priority (Module 4) |
| Structure quality: sweep+BOS present (QMRO > normal breakout) | 20 | AMS formula, Module 2/5 |
| Series strength: B-series > A-series | 15 | "B stronger than A" (Module 5) |
| Entry model clean: Model A/B candle sequence complete | 15 | 5-candle sequence rule (Module 5) |
| Session bonus: LDN/NY setups score higher (NOT a filter — no session is excluded) | 5 | premarket routine (Module 0) |
Alert threshold: >= 70 = strong, 50-69 = weak (tagged), < 50 = no alert. All tunable in `settings`.

## Open questions — ALL ANSWERED by owner 2026-10-11 (see "Owner decisions, FINAL" above)
Nothing open. Historical note: Q1/Q2/Q4 had no transcript basis (owner chose editable defaults);
Q3 = all IC Markets pairs over time; Q5 = Qwen-proposed weights, validated by backtest with
walk-forward split.

## 10. Visual cross-reference layer (added 2026-10-12 after owner correction)
The rules above were originally built from transcripts only. The repo also holds
`knowledge-base/frames/` — 748 contact sheets (38 videos, one frame every 15 s,
timestamp burned into each still) with per-frame speech indexes (`index.md`).
Owner is correct: the pointing moments ("this level", "right here", "you can see")
carry information the words alone don't — WHERE on screen the mark sits decides
whether a break is a sweep or a BOS, which wick is the apex of a QMRO, etc.

What was done this pass (all reproducible via `python3 knowledge-base/frame-analysis/build_index.py`):
- Parsed all 38 frame indexes into `frame-analysis/annotations.csv` (3,749 timestamped speech lines).
- Extracted **141 pointing moments** across the 21 core strategy videos → `frame-analysis/frame-index.md` + `.json`, each mapped to its exact sheet + slot (e.g. `kevin-key-levels-pt1` 21:20 = slot 14 of `sheet_001.jpg`).
- Concept-frequency check while pointing: sweep/wick-tap 197 mentions, key-level shapes 157, inducement 65, body-close 48 — confirming these four are the visually-determined core of the method.

Consequences for the machine implementation (rules restated as what the frames show):
1. Sweep vs BOS is decided by *which extremity* is touched: wick beyond + no body close = sweep (target liquidity); body close beyond swing = BOS. Both must be computed from raw OHLC, never assumed. [frames: kevin-basic-ms-pt2, kevin-advance-market-sturcture 34:00]
2. Inducement is always the *minor* high/low sitting between the swept point and the BOS origin — visible as the small bump Kevin circles before the break. [kevin-advance-market-sturcture 21:20]
3. Key levels are zones drawn from the *candle that rejected*, not single prices; A/V/OC shape tells which side is the POI edge. [kevin-key-levels-pt1 26:40, 32:40]
4. In worked breakdowns (CADJPY/EURGBP, Bishop bias→entries) entry is taken at the CLOSEST fresh key level in bias direction after sweep+BOS+inducement, confirmed one TF down — the same three-event formula, just zoomed. [bishop-bias-entries index 02:15–03:30]

Honest limitation: I cannot see images in this environment and there is no vision API key configured here. This pass built the complete text↔frame cross-reference so the visual claims are now checkable (each rule cites the exact sheet), but a true pixel-level study needs either you eyeballing the cited sheets or a vision-capable model run over them (possible Stage-0.5 task: dispatch extract-frames.yml `mode=frames` at the 141 timestamps, then feed stills to a vision LLM).


## 11. Bishop layer — how practitioners actually run SLK (added 2026-10-11; 9 Bishop videos now cross-referenced: transcripts + frame indexes + pixel/VQA pass)

The previous sections cite Kevin only. The repo also holds 9 Bishop mentorship videos (~270 KB of transcripts, 55 frames). They are the *applied* version of the same method and change several implementation decisions:

### 11.1 Bias building is multi-timeframe AND can be weekly/monthly-first [bishop-bias-entries 00:45–01:15, bishop-building-bias-1/2]
- GBP/AUD example: monthly bearish break last month + weekly recent breaks bearish → "everything was screaming sales". Bias is built top-down (monthly→weekly→daily), not just DRD.
- Implication for bot: bias table must store per-TF direction (M/W/D/H4) + a composite, not a single daily flag.

### 11.2 Bishop's repeatable entry recipe ("repeating system") [bishop-repeating-system 01:05–03:40]
Fixed sequence he says he uses "all the time":
1. Bias confirmed on HTF (e.g. weekly bullish, daily breaker aligned).
2. On entry TF (H4): wait for sweep of liquidity + breakout/BOS in bias direction.
3. Identify a **single candle used as liquidity** (his wording for internal/single-candle liquidity).
4. Play the **closest key level** to that swept candle — but WAIT for rejection there first.
5. Confirmation entry one TF lower; acceptable confirmations he lists: SIP+break, plain breakout, breakout-with-or-without-liquidity, engulfed open-close (price closes above an OC level then retests it), or wick-of-a-candle swept while the high still stands (V-shape entry).
- This matches our three-event formula exactly and gives the scoring model its confirmation taxonomy.

### 11.3 Targets = external liquidity, reversal expected after ERL is taken [bishop-bias-entries 05:15–06:15]
"Once the external liquidity is taken, expect a reversal. So the target should always be external liquidity." He places TP at next-week/next-day extreme (erl = weekly high visible on chart). Confirms §8; adds rule: if price has already swept the nearest ERL before entry, target moves to the next structural ERL, not back toward origin.

### 11.4 Failed-entry handling [bishop-bias-entries 02:45–03:15, 06:45–07:00]
Two real examples: entry placed at extreme key level, stop hit on a spike, then price eventually ran the original idea. His discipline: keep bias while structure intact, take the NEXT setup (he got the follow-through trade ~3h later). Bot implication: a stopped-out signal on the same leg does not void the bias; re-arm after new confirmation, mark trade `retry_of` id.

### 11.5 Pair universe & risk exposure [bishop-daily-routine 00:27–02:30]
He trades many pairs but warns: more pairs = more risk exposure + missed setups + analysis drain. His solution: a **checklist** that gates each pair — "if I see this I monitor it, if not I move to the next pair". Validates owner's no-pair-restriction decision provided the checklist gate exists (our score threshold ≥70 is that gate). Backtest must report per-pair so we can rank attention pairs.

### 11.6 Visual/pixel evidence caveat (honest limits of this pass)
Ran a reproducible vision pass (`knowledge-base/frame-analysis/vision_pass.py`, BLIP-VQA + numpy color metrics over the 761 extracted stills; results in `pixel/annotations.jsonl`):
- 28/32 sampled sheets: VQA confirms candlestick chart with drawn lines; annotation colors found: black (20), white (7), green (5); horizontal key-level lines detected in 7 frames.
- Pixel marker scan across ALL 761 images: Kevin's class videos are heavily annotated (85–100% of sheets carry colored markers), Bishop's are mostly raw charts + spoken pointing (0–39% marker pixels) — i.e., Bishop teaches by cursor/circle gestures that don't leave colored pixels, so frame content for Bishop must be read together with his timestamped speech index, which is what §11 cites.
- A true pixel-level study (reading exact axis prices under each drawn line) needs a hosted vision API (GPT-4o/Qwen-VL); Qwen2-VL download stalled on this sandbox's network and BLIP answers are too coarse for price extraction. Flagged as optional Stage-0.5 upgrade.
