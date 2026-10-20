# Bishop supplementary source verification — 2026-10-20

This is an evidence review, not a claim that the trading engine reproduces these examples.
The new medium transcripts are the `bishop-defi-bishop-study-*` directories. Shorter legacy
slug transcripts and old supplementary notes are useful locators, not independent sources.
Sources below abbreviate the unambiguous long directory names: `bias1` = BUILDING BIAS PART1;
`bias2` = BUILDING BIAS PART2; `entries5` = Entries Part5; `bias-entries` = 10 Minute Part1;
`what-next` = 10 Minute Part2; `repeat` = 20 Minute Part1; `trades2` = 20 Minute Part2;
`trades3` = 20 Minute Part3 without `-1`; `routine` = DAILY ROUTINE.
Times are seconds from video start. `[T]` means transcript; `[F]` means inspected picture.

## Coverage and provenance

- Reviewed source passages in all nine unique Bishop sessions, particularly bias1's theoretical
  sequence, entries5's three execution paths, repeat's liquidity qualifications, trades3's
  timeframe tie-break and stops, routine's counter-weekly examples, and the worked bias-entries trades.
  This is a targeted review, not a claim that every transcript sentence or every sheet was read.
- Initial pictures inspected: bias-entries/sheet_001 (t0–480), bias1/sheet_002 (t500–980),
  entries5/sheet_001 (t0–480), entries5/sheet_003 (t1000–1480). Those references describe the
  ORIGINAL 25-tile sheets; the replacement 4-tile indexes use different sheet numbers. Preserve the
  timestamps as the stable citation. Drawings confirm the narrated cascade and distinct entry paths.
- IMPORTANT: those original Bishop sheets are ~2100×1180, 25 tiles each (~420px per tile),
  sampled every20s. They are not the 1280px-tile re-extractions that exist for the core course.
  Their axis labels/date text cannot support exact numeric replay acceptance criteria.
- Re-extraction from release originals is underway separately. Source video resolutions and
  hashes must be recorded, and exact labels inspected in those outputs before upgrading examples.
- The release's two Part3 assets (`...GB.mp4` and `...GB.1.mp4`) have the SAME declared SHA256:
  `ee73e7118df31d1f30524a204ffe5393bbfc05b87197f935fe01bd4687d45004`.
  Ten release videos therefore represent NINE distinct sessions; count Part3 examples once.
- Plug-and-play has a separate independent review in `plug_verified.md`.

## Confirmed and corrected rules

| ID | Status | Source and rule | Implementation implication |
|---|---|---|---|
| B01 | confirmed | [T bias1@60.4–177.6] V = buy; A = sell; bullish/bearish open-close levels are additional decision points. [T bias1@183.6–275.6] body closure through a level changes its use to the opposite direction. | Track role changes when the relevant candle closes. Shape, price, formation time and role-change time must remain auditable. |
| B02 | confirmed | [T bias1@373.6–450.3] key-level bias requires rejection, origin candle closure, then breakout OR sweep-and-break/BOS on the next lower timeframe. [T bias1@470.9–502.9] after daily confirms weekly, follow bullish H4 flow to external liquidity. [F bias1@500–620] W/D/H4 columns depict both directions. | A wick rejection alone does not produce confirmed higher-timeframe bias. Accept breakout as an alternative to sweep+BOS rather than requiring both. |
| B03 | new explicit branch | [T bias1@774.6–847.6] if weekly rejects but daily never gives the required breakout, daily candles rejecting the SAME weekly level can anchor a DAILY story; H4 must then provide breakout or sweep+break. [F bias1@780–840] repeats W level into D rejection and H4 sequence. | Preserve story origin (`D`) separately from level origin (`W`). Do not mislabel weekly bias confirmed merely because this daily fallback is valid. |
| B04 | confirmed | [T bias2@408.5–478.4,536.4–615.8] liquidity alternative: swept previous candle low/high + candle closure + next-lower-TF breakout OR sweep+BOS. A low sweep suggests high as draw; high sweep suggests low, subject to structure/target guard. | Key-level rejection and liquidity sweep are alternative origins, not mandatory simultaneous filters. Need a closed candle, not a current wick alone. |
| B05 | corrected universal hierarchy claim | [T routine@394.1–421.5] explicitly permits using D+H4 while W and D disagree: “leave the weekly and use my daily and my four hours.” [T what-next@455.2–480.0] GBPCAD daily bullish reversal while weekly bearish is deliberately taken. [T trades3@261.3–307.9] no daily confirmation for the weekly sale, daily buys align with monthly instead. | Default aligned mode may exclude these trades, but a universal W>D veto cannot reproduce ALL teaching examples. Tag counter-weekly/reversal setups and keep that mode explicit. Do not silently call them errors or omit them from fixtures. |
| B06 | confirmed | [T entries5@85.8–135.5,225.9–291.1] DIRECT H2: wait for H4 breakout candle CLOSED, scale to H2 breakout/sweep+break with single-candle OR structural liquidity; direct entry at closest relevant H2 KL. [F entries5@100–140] diagram labels H4 breakout → scale H2 → LQ/KL. | Separate execution model `direct_h2`. H4 direction is established before order eligibility; H2 has its own liquidity/KL, no additional H2 confirmation layer required. |
| B07 | confirmed | [T entries5@156.9–221.2] DIRECT H4: after breakout and liquidity formation, limit directly at relevant H4 KL anticipating liquidity sweep then expansion. Stop is below indicated area in bullish diagram. [F entries5@160–220] long risk box spans below the level. | Separate `direct_h4` model. A pre-existing liquidity pool must be known before order placement; don't demand that sweep already happened for a direct limit. |
| B08 | corrected binary taxonomy | [T entries5@293.6–365.2] CONFIRMATION: wait for price to trade into H4 KL and react, then use lower TF; waiting for H4 reaction candle to close is personal choice. LTF examples H3/H2/H1/M45/M30/M15/M5. [T entries5@378.2–453.1] breakout, sweep+BOS, or engulfing; first two personally preferred. | Three execution paths (H2 direct, H4 direct, confirmation), not merely a boolean aggressive/conservative flag. Reaction-close choice is different from B06's explicit H4 BREAKOUT-close requirement. |
| B09 | corrected narrow detector | [T repeat@263.9–355.9] liquidity need not be the immediate next candle and need not be only one candle; a series or drawn advanced structure can supply it. [T repeat@113.7–140.7] nearest relevant KL and rejection then LTF confirmation. | A mandatory exactly-next inside-bar detector is one restricted implementation choice, not the full teaching. Store liquidity source type and formation interval. |
| B10 | confirmed | [T repeat@153.6–230.1] low swept + high standing gives V-shaped entry; engulfed open-close level is another trigger, retested for buys. Pattern often appears as an engulfing one TF lower. | Support distinct named confirmation patterns. “Often” across TFs is corroboration, not a mandatory multi-TF equality rule. |
| B11 | confirmed tie-break | [T trades3@476.6–520.0] concurrent H2 and H1 breakout: chooses H2 because higher TF is stronger and price might never reach H1. | When genuinely simultaneous valid confirmations compete, prefer higher TF; do not use a future H2 signal to retrospectively suppress an earlier H1 trade. |
| B12 | corrected target default attribution | [T bias-entries@319.4–337.6] nearest external liquidity is Bishop's personal target. [T repeat@593.6–648.3] nearest external is selected before resulting ~3R is narrated. [T trades3@430.6–456.5] H1 external target deliberately slightly nearer. | Target is market level; R is resulting distance/risk. Fixed3R is an optional user/implementation choice, not a universal Bishop target. Freeze intended level when the trade becomes eligible. |
| B13 | confirmed protective target guard | [T bias2@815.5–890.0] after bullish breakout a sweep of breakout high can retrace to a nearby KL and resume upward; don't assume full far low will be reached against overall bullish structure. [T bias2@960.5–980.5] EURCAD's safest initial target is nearest liquidity. | Counter-structural sweeps use nearer liquidity; do not automatically target opposite full-range extreme. |
| B14 | corrected fixed-stop attribution | [T trades3@1287.7–1348.1] GBPUSD stop kept beyond nearby liquidity AND key level because price may normally sweep them before moving. [T repeat@638.7–648.3] stop above indicated high/KL; [T bias-entries@208.8–224.2] above high. | No universal 10–11pip rule in these Bishop passages. Actual teacher replay must use source-documented risk boundary, not force the owner's fixed-stop experiment into every example. Exact geometric zone construction still needs frame derivation; position-tool colors alone do not explain how the zone was selected. |
| B15 | confirmed workflow | [T routine@438.9–474.1,552.0–579.4] flag after daily direction is available, then monitor missing H4 breakout/liquidity/reaction. [T bias-entries@170.6–202.4] first entry misses; subsequent breakout produces another setup. | Maintain per-pair setup state and missed orders; new valid continuation may create another entry. Do not chase a missed retest or erase misses. |

## Chart examples located; numeric replay not yet verified

These are locators for acceptance fixtures, NOT invented dates or complete trade records.
No row below is a PASS from an engine.

| Source | Instrument and expectation | Observations that must be captured |
|---|---|---|
| bias-entries@50.6–247.8; picture@220 | GBPAUD sell, monthly+weekly+daily bearish, H4 breakout/liquidity; first retest missed, next H1 breakout entry. | Exact date/time, entry/stop/TP axis labels missing at current sheet resolution. Must preserve the missed first order. |
| bias-entries@247.9–348.2; picture@320 | JP225 buy, D rejection → H4 breakout → liquidity sweep → H1 sweep+BOS, nearest external target. | Actual ticker mapping, broker, date, fill/stop/TP; ~5R verbal estimate is not precise quote. |
| bias-entries@348.2–507.6; picture@480 | US30: initial engulfing buy stopped out, later H1-breakout buy to external. | MUST include loss and later entry as separate fixtures; first stop does not mean direction changed. |
| bias-entries@508.4–694.1 | EURGBP buy, D-only direction when monthly/weekly unclear; H2 breakout; personal choice not waiting reaction candle close. | Not evidence for globally mandatory W/D alignment; exact marked prices/date remain unreadable. |
| entries5@921.5–1170.3 | XAUUSD, weekly rejection/daily breakout, H4 reaction, lower-TF engulfing/breakout, direct alternatives shown. | Distinguish taken confirmation trade vs hypothetical direct entry; multiple drawn alternatives are not one accepted trade. |
| trades3@476.6–551.4 | GBPCAD buy using H2 instead of simultaneous H1. | Store competing TFs and selected H2; exact labels/date required. |
| trades3@647.5–677.3 | AUDCHF H1 engulfing loss. | Real losing trade; do not remove from validation population. |
| trades3@1281.3–1348.1 | GBPUSD H2 engulfing sale with stop beyond H4 liquidity/KL. | Actual stop geometry, not just engulfing wick; include nearby-liquidity sweep survival. |
| what-next@455.2–504.6 | GBPCAD daily bullish reversal against bearish W. | Explicit counter-weekly category, not an aligned-mode example. |

## Choices the source does not settle numerically

Do not silently import Kevin's parameters as Bishop's teaching. These remain implementation choices:
which turning points constitute the active external range; equal-price/tap tolerances; precise
liquidity-series segmentation; definition of engulfing (body-to-body vs closure through OC level);
formation and invalidation of imbalance zone; minimum gap size; timeframe search budget; expiry;
news/session hours and timezone; aggregate exposure; spread/slippage/commission; same-bar fill order.
Each needs a named setting, source/choice label, causal tests and an explicit evidence status.

Hard acceptance policy: all verified examples must match the source under THEIR documented model.
Unreadable or missing evidence is unresolved; a hypothetical aggressive stop cannot replace a teacher's
actual structural stop, and no date/price should be inferred from a successful backtest.

## Native-source frame follow-up and timestamp correction

Initial high-resolution re-extraction exposed an inherited extractor bug: `fps=1/15` selected
source frames around half an interval later than its output timestamp, while the script burned
`n*15` and used that value for transcript lookup. Both the examples reviewer and this reviewer
independently extracted native source@1395 and found an unfinished0.63RR EURUSD position tool,
where the sheet labeled1395 showed a later4.8RR state. Earlier candidate measurements from
those labels are withdrawn as exact-timestamp assertions; they described pictures, not the
claimed source instants.

`extract_frames.py` now selects source frames without clock resampling, burns their actual
source PTS, and records actual seconds in both index and timestamps.json. All Bishop outputs
are being regenerated with the correction; see bishop_frame_manifest.json for completed scope.
Retained core-course and plug-and-play sheets still have the old approximate output-clock
labels until separately regenerated. Source videos are outside the repository.

The independently checked native measurements are:

- EURUSD H2 FOREXCOM@1410: entry1.15330, final illustrated stop1.15280, target1.15589.
  At actual1395 the teacher is actively dragging the stop; that0.63RR tool state is not a
  separate accepted trade. Chart drawing starts Wed05Aug26 06:00, display timezoneUTC+1.
- XAUUSD H3 Saxo@1065: entry4079.56, stop4064.31, target4165.88, toolRR5.66.
  Earlier sheet label1065 described a later target manipulation; it is withdrawn.
  Chart drawing starts Wed05Aug26 02:00, display timezoneUTC+1.

Those tool-anchor times are not proven broker fill times. They are source plan observations,
not completed engine replay PASS claims. The fixture reviewer owns their formal evidence status.
