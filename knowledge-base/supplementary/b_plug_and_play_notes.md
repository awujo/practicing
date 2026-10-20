# Bishop Supplementary: "This Plug and Play Forex System Changed How I Trade"

## Content type
A live community call (~52 min), transcribed via `faster-whisper` on GitHub
Actions (see `.github/workflows/transcribe.yml` -- this session's own
network blocks huggingface.co, the model-weight host, so transcription
can't run locally). **Caveat up front**: the auto-transcript is noisy in
many places -- common, identifiable mis-hearings include "God/gets is
respected" for "gets disrespected", "HFK level" for "A-shape key level",
"for our high/low" for "4H high/low", "infinity"/"the ability" for
"liquidity", "record"/"record structure" for "break"/"break of
structure", and "kind of"/"country" for "candle". Read the notes below
as a best-effort reconstruction, not a verbatim quote, and re-check
against `knowledge-base/videos/plug-and-play/transcript.txt` directly if
a specific detail matters.

This is Bishop (not the main mentor -- he credits "Isaac" as the mentor
who originated the underlying concept) teaching HIS OWN community his
personal execution system, explicitly named "plug and play." Three real
worked examples given in depth: a NAS100 4H/daily setup, a Gold (XAUUSD)
weekly->daily->3H/1H example, and an EURJPY weekly->daily example; a
fourth, USDCHF, is sketched briefly in response to an audience question
near the end.

**Visual verification pass (full)**: beyond the initial 2-frame spot
check that fixed the pair names (EURJPY, not "USDJPY"/"ULJPY"; USDCHF,
previously missed entirely), a fuller pass extracted ~185 frames across
the whole video plus a dense (8s-interval) set within each of the 4
worked-example windows (NAS100, Gold, EURJPY, USDCHF -- 138 frames), all
read directly. Findings:
- Real horizontal rays / price-range tool marks are visible at concrete
  prices in every example (NAS100 ~21,158 / ~21,449.4 / ~21,114.5 on the
  4H chart; Gold a long horizontal ray at ~3,140 spanning the full
  visible daily range, consistent with a weekly-timeframe anchor, plus a
  sketched sweep-low -> swing-high -> sweep-low structure around
  3,117-3,260; EURJPY a ~163.31 imbalance/FVG zone and a second reaction
  level around ~161.8-162.0; USDCHF a ray at ~0.8256-0.8257 on a
  30-MINUTE chart, matching the transcript's "let me use 30 minutes"
  line) -- confirms these are genuinely marked levels, not just verbal
  description.
- No new named terminology appears written on-screen anywhere -- every
  Bishop term (including "conservation sector") is spoken only, never
  typed/labeled on a chart.
- Much of the video between the 4 labeled examples is either talking
  with idle pencil-tool doodling (loose squiggles/arrows, not real
  levels) or browser-tab switches to X/Twitter -- including one where
  Bishop reads "plug and play"'s definition straight off a ChatGPT
  answer (word-for-word match to what's quoted below) and shows other
  students' (@The_4thMan, @chaxbtbg) trade-result posts captioned "plug
  and play" as social proof that the term circulates across the
  community, not just from him.
- No corrections needed to the mechanical claims below (daily-
  confirmation fallback, conservation sector definition, aggressive-
  entry-style confirmation) -- the visual evidence is consistent with,
  not contradictory to, the audio-based draft in every case checked.
Full frame-by-frame notes: see the session's scratch findings log if
still available; not committed here since it's a working artifact, not
a source document.

## What "plug and play" actually means (mostly a discipline framework,
not a new pattern)
Bishop's own definition, repeated several times: "a system or strategy
that is ready to use immediately with little to no configuration --
just apply it to your chart." His stated motivation: he sees traders
with access to all the same course material still struggling to find
"their own system," switching approaches instead of committing to one.
The core message is OWN one consistent, mechanical process end-to-end
(bias -> entry -> stop) so execution requires no in-the-moment
discretion or "refinement." This is a discipline/consistency framing
layered on top of the already-documented mechanics, not a competing
strategy.

## Two named ways to build bias (stated as interchangeable alternates,
not sequential steps)
1. **Key-level-based**: price rejects a key level and CLOSES beyond it
   in the reaction direction (`is_disrespected()` in key_levels.py,
   already implemented).
2. **Liquidity-based**: price SWEEPS a prior high/low (e.g. previous
   weekly high) and CLOSES back inside it -- no rejection-from-a-level
   needed, just a sweep+reclaim of that swing extreme. Leaves the swept
   level "still standing" as the next target.
Bishop uses whichever is present on a given timeframe -- not "try A,
then B," but "look for either."

## NEW: a daily-confirmation FALLBACK when the daily doesn't
independently confirm
This is the most concrete new mechanical rule in the video, and the
closest match to what plug-and-play was described as in chat (a
fallback used when the primary setup doesn't cleanly form):
- Normal case: Weekly gives ONE of (rejects+closes-below /
  sweeps-previous-high+closes-below), THEN Daily must ALSO give one of
  (breakout / sweep+break of structure) in the same direction before you
  proceed to entries.
- **Fallback**: if Daily does NOT give either of those two conditions,
  check whether Daily has come back and tested/rejected that SAME weekly
  key level at least twice ("rejected twice, closed below"). If so,
  treat that repeated respect as sufficient evidence on its own ("the
  market can't tell stories" -- repeated respect of the same level IS
  the story), and drop straight to the 4H timeframe -- but now only
  require ONE of (breakout / sweep+break), not both, before looking for
  entries. The repeated-daily-test substitutes for the missing
  independent daily confirmation, and the bar on the timeframe below is
  relaxed accordingly.
- **Backtester implication**: this is a genuinely new decision branch,
  not currently in `bias.py` or `runner.py`'s liquidity-cascade gate --
  worth implementing as an explicit fallback path once the primary
  breakout-based bias/gate logic has been validated against real data.
  Maps onto `count_tests_before_disrespect()` / `is_qmr_level()`
  (already implemented for key-level ranking) applied to the BIAS
  timeframe-cascade step itself, not just entry-level ranking.

## NEW: "conservation sector" -- Bishop's named compound entry signature
The specific key-level signature Bishop plays for entries, given a name
for the first time across all Bishop material processed so far. A key
level qualifies as a "conservation sector" when ALL of:
1. It's disrespected (flipped) in the bias direction.
2. It's overlapping an imbalance/FVG.
3. It has liquidity/equity resting above or below it (i.e. there's a
   nearby untaken high/low the market still needs to visit).
Additionally, he prefers levels that "sponsored" a real prior leg (i.e.
the level actually anchored/originated a genuine prior directional move)
over an isolated pattern that happens to meet the 3 conditions but
didn't really drive price before.
- **Refines `ranking.py`**: conditions 1-2 already map onto
  `imbalance_overlap` (Phase 2's ranking factor #1) and the
  disrespect/QMR logic already in `key_levels.py`. Condition 3
  ("resting liquidity nearby") is NOT currently one of the 4
  `DEFAULT_WEIGHTS` factors -- this is a candidate 5th ranking factor,
  or possibly a required gate rather than a weighted factor (Bishop
  describes it as something he checks for directly, not something he
  trades off against the others).

## NEW (clarifying, not a new rule): "plug and play" execution IS the
aggressive entry style, with an explicit "then walk away" habit attached
Restated near the end as the actual operational recipe: once a
conservation-sector level is identified in the bias direction, "set your
limits, set your stops, go about your way, come back after two, three,
or four hours, and see what price has done -- there are only two
expectations: either it's TP'd, or it's still going the right way."
This confirms plug-and-play's entry mechanic is the SAME aggressive
entry style already in `entries.py` (`aggressive_entry_price()` --
enter directly at the key level via a resting limit order, no waiting
for lower-timeframe confirmation candle) -- not a third entry style.
The "walk away, don't babysit the chart" part is a live-trading
operational habit (a backtester has no equivalent to babysitting
anyway), not a new detection rule.

## Reconfirmed
- Single Candle Formation / structural liquidity (Video 18, and Bishop's
  own "Repeating System" video): after a breakout candle, if the very
  next candle's low (bullish case) rests INSIDE the breakout candle's
  range, that low serves as IRL feeding the breakout candle's own high
  as ERL -- straightforward continuation setup. If that clean internal
  candle does NOT form, price instead tends to sweep the prior EXTERNAL
  liquidity, reverse, and build internal liquidity closer to a nearby
  KEY LEVEL instead -- i.e., absent a clean SCF, fall back to the
  nearest key level as the reaction point. Matches
  `structural_liquidity_points()` / the runner's liquidity-cascade gate
  conceptually; no new mechanic, just reconfirmation with the "what if
  the clean single-candle case doesn't form" branch spelled out again.
- "Daily beats 4H" / top-down cascade, confirmation entry taken on
  whichever lower timeframe looks "cleanest" (Bishop explicitly scales
  from 4H down through 3H/2H/1H/30min case by case) -- reconfirms the
  already-documented flexible-confirmation-timeframe note.
- "Don't marry a bias" / patience discipline, "the market can't tell
  stories [only price action can]" -- consistent with prior Bishop notes
  on discretionary judgment and not forcing entries.
- Open-close (2-consecutive-candle) key levels, shown concretely in the
  NAS100 example flipping bias multiple times (used for buys, got
  disrespected, swept, came back and got used for sells, disrespected
  again) -- matches `detect_open_close_level()` exactly, no new mechanic.

## Open items
- Video quality/ASR noise (see caveat above) still applies to the exact
  WORDING of spoken rules like the daily-confirmation fallback and
  "conservation sector" -- the visual pass confirmed the chart-level
  mechanics (real levels, real price marks) but can't verify spoken
  rule wording, since neither term ever appears written on-screen. If
  the "daily confirmation fallback" or "conservation sector" rules get
  implemented, it would still be worth a second listen against the raw
  transcript (or the source video directly) to confirm the exact
  wording before treating either as a hard rule.
- The user's own chat description of plug-and-play ("mainly used as a
  continuation if the original setup was missed") doesn't map cleanly
  onto anything stated this explicitly in the video -- the closest match
  is the daily-confirmation fallback above, but that's a bias-cascade
  substitution, not literally a `trade_kind == "continuation"` entry
  fallback in the codebase's existing sense. Worth confirming directly
  with the user before encoding it either way.
- Not yet implemented in the engine: the daily-confirmation fallback
  branch, and "resting liquidity nearby" as a ranking factor/gate. Both
  flagged in `runner.py`'s module docstring as follow-ups, not silently
  skipped.
