# Consolidated Strategy Rulebook (Living Document)

Built incrementally from the mentor's video course. Updated after each video
is processed. This is the source of truth we'll eventually translate into
precise backtestable code.

**Methodology family**: Smart Money Concepts / ICT-style price action
(market structure, liquidity, imbalance/FVG, sessions) with the mentor's own
terminology layered on top ("key level", "killer" shapes, "storyline").

Status: 16 of 18+ videos processed (Video 1: orientation, Video 2: admin +
pair-scanning philosophy, Video 3: full basics-to-advanced structure
foundation + consolidation/manipulation framework, Video 4: core
structure/liquidity framework, Video 5: liquidity types/forms + sequential
liquidity rule, Video 6: liquidity forms + Asian session setup, Video 7:
defined ranges + range cycle, Video 8: range examples + Asian session
4H-candle definition + news-event caveat, Video 9: the top-down
storyline/bias process — ties everything together, Video 10: extensive
live application of the storyline process across weekly/monthly
timeframes, Video 11: precise key-level definitions — RESOLVED the
V-shape/A-shape/open-close question, Video 12: mechanized IF-THEN
algorithm framing + IRL-necessity nuance for origin vs continuation
trades, Video 13: exhaustive confirmation-entry decision tree + mechanized
stop-loss placement rules, Video 14: same decision tree restated as 3
pattern-recognition entry types + explicit 70-80% win-rate quote + trade
stacking concept, Video 15: single live Gold trade demonstrating all 3
Video 14 patterns recurring fractally across 4H/1H/15min + "pick one
entry system and stay with it" discipline principle, Video 16: breakout
vs. sweep+break-of-structure distinction + "storyline starts/ends on same
timeframe's key level" exit rule + bias-flip confirmation state machine —
significant new codeable mechanics). Course turned out to be 18 videos
(not 17), and a supplementary set of study videos + a chart-examples PDF
from a fellow student (Web3Bish0p / Defi Bishop on X) is also being
incorporated.

**The framework's own name**: he calls it **"SLK" = Structure, Liquidity,
Key level**.

---

## 1. Core Mental Model

Price is always doing exactly two things:
1. **Attacking liquidity** (sweeping resting stops/orders)
2. **Rebalancing an imbalance** (filling a fair value gap)

Every setup = identifying WHERE price needs to attack liquidity, WHERE the
imbalance needing rebalance is, and at WHAT specific price level (inside that
imbalance) price is expected to react.

## 2. The Top-Down Storyline Process (THE master bias-building algorithm)

This is how a trade thesis actually gets built — ties every other section
together. Three nested checks, each confirmed by scaling one timeframe down:

### Monthly (once/month)
1. Check how the previous monthly candle closed relative to a monthly key
   level -> sets bias for the new month.
2. Confirm by scaling down to Weekly: look for a weekly sweep+break OR a
   weekly engulfing candle in the bias direction.
3. Scale down again to Daily to find actual trades.
4. Keep trading that direction until the monthly-implied move is exhausted.

### Weekly (every week, e.g. Sunday)
1. Check how the previous weekly candle closed relative to a weekly key
   level -> sets a directional lean, but NOT sufficient alone.
2. Confirm on the Daily: sweep+break, OR an engulfing candle, OR price
   returning to tap a previously-disrespected key level.
3. Until daily confirms, treat the weekly-implied move as possible
   retracement only. Journal what each timeframe shows and why.

### Daily routine (every day, Daily vs 4H)
1. Compare Daily vs 4H.
2. **Priority rule: Daily beats 4H.** If daily shows one direction but 4H
   reacts from a key level suggesting the opposite, the 4H move is
   retracement, not reversal.
3. Scale down further (1H -> 30min) for entries, always in the higher
   timeframe's direction.

### Refinements this process adds to earlier rules
- Candle-close discipline (wick vs. close, Section 4) matters **even more**
  on higher timeframes (weekly/monthly) than lower ones.
- Key levels are dual-purpose: usable as entries AND as the nearest
  stop-loss/invalidation reference point, not just entry triggers.
- **Induced-move trap**: a genuine-looking counter-trend bounce can exist
  specifically to induce the wrong side into a bad position before price
  resumes the higher-timeframe direction — treat counter-trend reactions
  against a confirmed bias with suspicion.
- **Data feed caveat**: candle closes can differ slightly between
  brokers/feeds near key levels — our backtester needs one consistent
  historical OHLC source and shouldn't assume exact tick-for-tick match
  with his TradingView/Oanda feed at the margins.

### "Breakout" vs. "Sweep + Break of Structure" — precise distinction
(Video 16)
Two visually distinct sub-patterns BOTH confirm timeframe-sync/directional
order flow when scaling down from a higher-timeframe key-level reaction:
- **Sweep + Break of Structure (BOS)**: the "textbook" pattern — price
  sweeps a prior swing point (wick through), reverses, then breaks/closes
  through a structural point, producing a visible lower-high-then-lower-low
  (or mirror) sequence. Stated to be the LESS common of the two on higher
  timeframes.
- **Breakout**: the MORE common pattern actually seen — a more direct,
  continuous push through the external range liquidity / prior extreme,
  WITHOUT a prior sweep-and-reverse. The default expectation, not the
  exception.
Both are equally valid confirmation signals; a confirmation-detection
function should accept EITHER shape, not require the stricter sweep+break
pattern exclusively.

**Cascade mapping rule**: when a higher timeframe shows a plain
"breakout" (not sweep+break), the NEXT timeframe down typically resolves
into a proper liquidity-sweep-and-break-of-structure. i.e. "breakout" one
level up commonly maps to "sweep+break" one level down — useful as an
expected-pattern lookup when scaling down for confirmation.

### Bias-flip confirmation state machine (Video 16 — precise, codeable)
A higher-timeframe bias should be considered FLIPPED (e.g. bearish ->
bullish) only when ALL of the following hold, not on a single reaction
alone:
1. Price trades into the NEXT key level on the storyline's ORIGIN
   timeframe (e.g. next weekly key level if the storyline was built from
   weekly).
2. Price rejects from it AND closes in the new (opposite) direction
   (candle closure / R&C).
3. **AND** the next lower timeframe (e.g. daily) ALSO fails to give any
   further continuation confirmation (no breakout, no sweep+break) in the
   ORIGINAL bias direction.
If the higher timeframe closes the "wrong way" at condition 2 but the
lower timeframe still confirms continuation in the OLD direction, the
bias is NOT yet flipped — keep trading the original direction until the
lower timeframe stops confirming it. Resolves a real ambiguity: a single
higher-timeframe reaction does not by itself flip the bias.

### Cross-confirmed pipeline (from Web3Bish0p / Defi Bishop, independent
source, same underlying mentor)
A public diagram from a fellow student formalizes this exact process with
clean labels worth reusing directly:
**BIAS** (built from **M/W/D/4** = Monthly->Weekly->Daily->4H, then
**"Immediate LTF"**) -> **CONFIRMATION**, labeled **"C.E" (Confirmation
Entry)**. Bishop's material gives the most concrete C.E definition seen so
far: once Daily+H4 bias align, drop to a 2-hour chart and wait for an
**engulfing candle** as the actual entry trigger.

## 3. Liquidity Framework

- **Internal Range Liquidity (IRL)**: minor liquidity resting inside a range
  (inducement points, small swing highs/lows).
- **External Range Liquidity (ERL)**: liquidity at the range extremes (major
  swing high/low).
- Expected cycle: sweep IRL -> expand to sweep ERL -> reversal -> new range
  origin. Repeats. Applies across ALL timeframes, not just intraday — same
  cycle shows up in daily/weekly swing highs and lows.

### Forms of liquidity (concrete taxonomy)
- Previous daily high / low, previous weekly high / low, previous monthly
  high / low
- **Asian session high / low** (see dedicated Asian-session setup below)
- **Trendline liquidity**: a series of consecutive higher-lows or lower-highs
  after a structure break, acting as a **magnet** drawing price back before
  the main trend resumes. Use the *last point* on that sequence (the "last
  resort") as the liquidity reference — no need to draw the actual
  trendline. Clearing this magnet zone is why momentum often "kicks in
  suddenly" right after an inducement-based entry.
- Multiple old highs/lows can stack as sequential pools, swept one after
  another in the direction of the move.
- Explicitly NOT used: double top/double bottom patterns, "central bank
  dealer's range" — deliberately excluded in favor of the minimal
  structure+liquidity+key-level system.

### Sequential liquidity rule (per-timeframe alternating target)
Once one side of a timeframe category's liquidity is taken, the next
target flips to the OPPOSITE side of that SAME category:
- Previous daily high taken -> next target = previous daily low (and vice
  versa)
- Previous weekly high taken -> next target = previous weekly low (and
  vice versa)
- Previous monthly high taken -> next target = previous monthly low (and
  vice versa)
- Asian low taken -> next target = Asian high (and vice versa)
A simple, directly-codeable alternating state machine per timeframe
category. These forms can also double as exit reference points, not just
entry framing (same dual-purpose principle as key levels).

### "Structural point(s)" confirmation rule (refined)
Before trusting a directional/structural bias, price should take out ONE
OR TWO structural points (each also an internal range liquidity point) in
the same direction — **not always exactly two**; sometimes a single break
is sufficient. Treat two as the common/typical threshold, not an absolute
rule.

### Consolidation & Manipulation Framework (non-trending markets)
When price is ranging rather than trending, its purpose is **engineering
liquidity**: building buy-side liquidity above the range and sell-side
liquidity below it. Two possible resolutions:

**A. Manipulation + Displacement**: price sweeps ONE side of the range's
liquidity, then gives an immediate, strong **displacement** move in the
opposite direction, confirming the new trend. Asian session is the most
common source of this consolidation (ties to the Asian-session setup
below).

**B. Break and Retest** (no manipulation): price breaks out directly with
displacement (no prior sweep), then retraces to retest the SAME key level
that has been respected multiple times before. **Quantified estimate**:
~80% probability of continuation in the breakout direction if that level
has inducement liquidity nearby and overlaps an imbalance — a testable
number for backtesting validation.

### Order-block inducement mechanics ("your stop loss is my entry")
Retail traders buying from an order block typically place stop-loss just
below it — creating a predictable cluster of resting stops. Liquidity-
aware entries target that exact cluster location since price is
statistically drawn to sweep it. Practical implication: **inducement
liquidity commonly forms just beyond order blocks/key levels**, precisely
where retail stops cluster — a useful heuristic for identifying inducement
zones in code.

### The Asian-Session Setup ("London setup using key levels")
1. Mark the Asian session high/low for the day.
2. Price sweeps the Asian low (or high) -> acts as internal range liquidity.
3. Price reacts at a key level overlapping an imbalance near that sweep.
4. Target: the opposite Asian extreme.
5. Frequency: ~1-3x/week, called out specifically for GBPUSD.

**Exact session definition** (confirmed from his indicator settings):
Custom TradingView indicator "AsiaSessionHighLowMidLines", session window
**17:00-00:15**, chart timezone **UTC-4 (New York)**. Must confirm DST
handling when building the backtester rather than hardcoding a UTC offset.
Cross-confirmed via a second, independent definition: **Asian session = 2
four-hour candles** — consistent with the clock-time window (~7h15m ≈ two
4H candles). The 4H candle that completes the Asian session can itself
serve as inducement if price approaches but doesn't tap it before London
continues the move.

### Daily/weekly "engulf but don't tap" inducement pattern
When a daily/weekly candle engulfs the prior candle's range while trading
close to a previous key level but does NOT touch/tap that key level, the
untouched-but-approached candle itself becomes inducement/internal range
liquidity. Expected sequence: take out that candle's high/low -> tap the
original key level -> continue toward the next liquidity target.

## 4. Defined Ranges & Range Cycle

A range/swing point is only valid once BOTH conditions are met:
1. **Sweep of liquidity** (a wick through a prior high/low)
2. **Break of structure** (price then breaks/closes through a structural
   point in that direction)

### Strong Low / Strong High / Weak High / Weak Low
- **Strong low** (bullish range): the sweep+break origin point of the range.
- **Weak high**: the range's primary target = External Range Liquidity (ERL).
- Strong high/low updates forward every time a new valid sweep+break occurs
  — not a fixed point. To find the current reference point, "look to the
  left" to the most recent valid sweep+break.

### ABC naming convention
A leg = strong low (sweep+break origin). B leg = inducement/internal range
liquidity. C leg = weak high = external range liquidity (target).

### Range Cycle
A range starts with sweep+break and ends the same way (sweep+break), which
simultaneously starts the next cycle. Within a range, price works through
successive internal range liquidity points, stopping at the "last resort
liquidity" (the IRL point closest to the strong high/low) before continuing
toward the external range liquidity.

**Core rule**: after every external range liquidity is taken -> expect
**reversal**. After every internal range liquidity is taken -> expect
**continuation**. Most applicable on lower timeframes (15m/30m).

### CRITICAL rule: wick-sweep vs body-close-break
The single most precise, directly-codeable rule extracted so far:
- Price **wicks through** a level but candle **does not close beyond it** ->
  structural shift NOT confirmed. ~90% probability price returns to use
  that level as further internal range liquidity before continuing in the
  original direction. Treat as invalid/low-probability for redefining
  strong high/low.
- Price **closes beyond it** (body close through) -> validly confirmed.
- Must compare **close price**, not high/low wick, against the reference
  level when implementing structure-break detection in code.

### Alternate pattern: "engineered internal range liquidity"
Sometimes after a strong low forms, price fails to cleanly break either
side (contracts instead), then comes back to sweep (not necessarily close
through) the strong-low area before continuing in the original direction.
Same wick-vs-close distinction applies to whether the external range
liquidity is still "pending" in this pattern.

## 5. Entry Setups (two variants, both derived from the same two conditions)

### A. "Origin of the move" (highest quality, hardest to catch)
Liquidity sweep + immediate break of structure (BOS) confirms order flow.
Entry at a "key level" overlapping inside a fair value gap, right where the
order flow was confirmed.

### B. "Continuation setup" (preferred/most repeatable — stated as "the one
setup I'd trade for the rest of my life")
Used when the origin move is missed:
1. Find a key level that was previously **disrespected** (broken)
2. Wait for a new **inducement liquidity** to form close to that level
3. That level (overlapping an imbalance) + nearby inducement = entry trigger
Requires patience; do not force it before inducement forms.

**IRL necessity nuance (Video 12)**: IRL formation is effectively
*necessary* to validate an ORIGIN trade, but *optional* for a CONTINUATION
trade. If a continuation setup's engulfing/key-level tap occurs without a
subsequent IRL forming, enter directly anyway with a **tighter stop**
(just past the engulfed candle's extreme + 1 pip, instead of the usual
10-11 pips). Two variants to implement separately.

### The mechanized IF-THEN framing (Video 12 — closest thing to
pseudocode given directly)
"If A,B,C happens, we do X,Y,Z":
- **ABC**: price taps a key level -> rejects -> closes beyond it (a "R&C",
  reject-and-close) in a direction.
- **XYZ**: scale one timeframe down -> look for EITHER a liquidity sweep +
  break of structure, OR an engulfing candle, confirming the same
  direction -> expect the next candle to serve as IRL -> gets swept -> key
  level (ideally overlapping an imbalance) taps -> continue.

### "No POI" philosophy
Does NOT pre-mark anticipated reaction zones in advance (no forward-
looking order-block boxes). Key levels are identified **reactively**,
based on realized candle closes as they happen. Backtester implication:
level detection must be based on confirmed historical closes, not
speculative zones drawn ahead of price reaching them.

### Bias doesn't always require the full top-down cascade
Video 9's full Monthly->Weekly->Daily->4H cascade is the thorough method,
but reading "what the current structure is saying" on a **single relevant
timeframe** (e.g. just 4H) is a valid, faster alternative when that
timeframe's structure is already clear on its own.

### Disrespected-level priority refinement
When a level is disrespected, prefer the **same, more recently
disrespected level** as the likely next reaction point over a more
distant "extreme" level, when both are candidates (refines Video 11's
two-target strategy with a recency/proximity tiebreaker). **Quantified**
(Video 13): ~70% chance price does NOT return to the original "extreme"
key level and instead returns to a newer, closer disrespected open-close
level first.

### The confirmation-entry decision tree (Video 13 — exhaustive, directly
codeable)
After price takes IRL and rejects from a key level, scale one timeframe
down. What happens next falls into one of these branches:
1. **Clean confirmation**: the lower-timeframe candle closes back through
   the key level (often through the IRL too) -> direct continuation.
2. **Slow grind, fresh IRL required**: two candles form a new open-close,
   a third taps the original IRL, an even-lower-timeframe engulfing
   creates a new A/V-shape level, and the NEXT candle after that serves as
   a fresh IRL that must be swept before continuing.
3. **Engulfing without fresh IRL**: same engulfing as above, but price
   taps the new key level directly and continues, no separate IRL forms
   first (the "optional IRL" continuation variant from Video 12).
4. **Nested disrespected-open-close**: instead of respecting the new key
   level, two more candles form ANOTHER open-close that then gets
   disrespected — triggering the ~70% "return to the closer level" rule
   above.

**Restated as 3 execution-facing patterns (Video 14 — same mechanics, "what
you actually see" framing)**: (1) engulf -> direct mitigation of the new
key level -> continue [= branches 1/3 above]; (2) engulf + break of a
fresh 2-candle open-close -> return specifically to that open-close, not
the original extreme [= branch 4 above]; (3) engulf -> next candle
approaches but doesn't tap the new key level -> that candle becomes fresh
IRL -> must be swept first [= branch 2 above]. Explicit **70-80% win-rate**
quote for the continuation setup overall (matches Video 11's quantified
70-80% pattern-reliability figure — same number, applied as win rate here).

### Key-level shapes (RESOLVED — precise definitions from Video 11)
Key levels are marked on **closing prices**, not wicks/highs-lows.
1. **A-shape**: a peak/apex-shaped reversal (price rises into it then
   reverses down, resembling the letter "A"). Default use: **selling**.
2. **V-shape**: a trough-shaped reversal (price falls into it then
   reverses up, resembling "V"). Default use: **buying**.
3. **Open-close**: two consecutive same-direction candles whose open/close
   prices overlap. Two down candles -> sell continuation; two up candles
   -> buy continuation. An engulfing candle consuming one/both of these is
   functionally equivalent to a body-close break of a V/A-shape level.

**Universal flip rule**: ANY key-level type flips its default bias if
price **disrespects** it — a body close, with an impulsive move, beyond
the level in the opposite direction. Once flipped, expect the opposite
reaction at that same level going forward.

**Two-target strategy after disrespect**: (1) SAME level, if inducement
forms near it first before price taps back and continues — high
probability; or (2) "the extreme" — a further level (e.g. the original
shape's far point) if no inducement forms first — lower probability
fallback.

- Key levels can also be a plain "open close" level, interchangeable with
  V/A-shape killers; use whichever valid type is present, no fixed
  preference.
- **Quality signal**: a key level with an imbalance overlapping it performs
  better than one without — confirmed directly, not just incidental.
- **Quantified reliability** (Video 11): the pattern "sweep previous-period
  high/low -> engulf -> next candle serves as inducement close to the
  resulting key level -> tap -> continue" holds **70-80% of the time** on
  4H and Daily timeframes specifically — a genuinely testable number for
  backtesting validation, not vague confidence.

### Entry style spectrum: Aggressive vs. Conservative (both sanctioned —
build/test both in the backtester)
- **Aggressive**: enter directly once the key-level+imbalance setup is
  fully formed, without waiting for inducement/confirmation, using a wider
  stop (~10-11 pips) for breathing room. Accepts more drawdown/whipsaw
  risk to avoid missing moves that never give a clean confirmation.
- **Conservative**: wait for a full confirmation entry (lower-timeframe
  trigger — e.g. Bishop's H2 engulfing candle) before entering. Fewer
  false starts, but risks missing moves that run without ever confirming.
- Presented as legitimate personal-style choice, not one superior to the
  other — should be implemented and tested as two separate variants.

### "Pick one entry system and stay with it" (Video 15, discipline
principle, not a mechanical rule)
Explicit advice: rather than situationally choosing between the 3
confirmation-entry patterns (Section 5 above) trade-by-trade, commit to
ONE preferred pattern as a personal default and apply it consistently.
Does not change which patterns are valid — surfaced here as a
configurable "entry style" parameter/preset for the bot (e.g. "always
prefer Pattern 1" vs. "always prefer Pattern 2") rather than a dynamic
per-trade choice, useful for backtesting each preset in isolation to
compare performance.

### 4H timeframe specifically emphasized (Video 15)
Beyond the general "higher timeframe for bias" guidance (Section 7),
4H is called out repeatedly and specifically as the preferred timeframe
for identifying the key-level reject-and-close (R&C) that anchors the
full cascade down through 1H/30min -> 15min -> 5min execution. A live
example showed the identical entry pattern (open-close -> IRL -> engulf
-> retest) recurring self-similarly at 4H, 1H/30min, and 15min in the
same trade — supports treating the pattern-detection logic as scale-
invariant/fractal across timeframes rather than timeframe-specific.

## 6. Trade Management

### "Storyline starts and ends on the SAME timeframe's key level" (Video
16 — major exit-targeting rule)
If a directional bias (storyline) originates from a reaction at a key
level on a given timeframe, the storyline is expected to conclude
(reverse) at ANOTHER key level on that SAME timeframe — not at the
lower-timeframe key level the actual entry trigger came from. Example:
bias built from a **daily** key level -> 4H breakout -> 1H sweep+break ->
entry taken on 1H. The IDEAL exit target is the NEXT **daily** key level,
not the 1H or 4H level. Applies recursively at every scale (a 4H-built
storyline targets the next 4H key level; a weekly-built one targets the
next weekly key level, etc.) — exit-target selection must key off the
timeframe the ACTIVE bias originated from, not the entry-trigger
timeframe.
- **Explicit cautionary pattern**: taking profit/breakeven at a lower-
  timeframe key level because price "looks like it's reacting there"
  often means missing the real move that continues on to the actual
  higher-timeframe target — "your entry was right but your exit was
  wrong," stated as a common, specific mistake.
- **Tiered take-profit refinement**: the standard IRL->ERL progression
  (Section 3) still applies first at the ENTRY timeframe — e.g. if entry
  came from a 4H setup, the first natural take-profit is that 4H
  timeframe's own external range liquidity (price may retrace there
  before continuing toward the ultimate higher-timeframe target). Exit
  planning therefore has at least two tiers: a nearer partial target at
  the entry-timeframe's ERL, and the ultimate target at the next key
  level on the bias's origin timeframe.

- Primary target: **1:3 risk-reward** — stated as the repeatable bread-and-
  butter target. Occasionally extends further (1:6 seen once).
- Explicit lesson: take the 1:3 when it's there — don't hold out for more and
  risk giving it back.
- Stop-loss: structure-derived (placed relative to the imbalance/key level),
  not a fixed pip value — one example used ~10 pips, not a universal rule.

### Mechanized stop-loss placement (Video 13, direct student Q&A)
- **Origin trades**: stop just beyond the strong high/low (the sweep+break
  origin point) plus extra room to breathe — the safer, structure-true
  placement.
- **Continuation trades**: personal preference for a fixed **~10 pips**
  (more aggressive) rather than the full structural distance, trading
  faster 1:3 realization against higher risk of getting stopped by a
  liquidity-hunt sweep before the real move.
- **Padding rule**: stop placed at the reference high/low + **1 pip (or
  0.5 pip)** buffer — a small fixed addition, not percentage/ATR-based.
- **Judgment nuance**: when multiple nearby levels exist, a stop above a
  more distant MAJOR structural high can be safer than one above a closer
  MINOR level, since minor levels get liquidity-hunted more easily — not a
  fixed rule, requires case-by-case judgment about which level is more
  likely to be swept as inducement first.
- Explicit real-trade admission: tight stops (~5 pips) have genuinely
  almost gotten stopped out before the correct move played out — a real,
  acknowledged risk of the aggressive-stop approach, not hypothetical.

### Trade stacking (Video 14, new concept)
Once a continuation trade is open, additional qualifying setups on a LOWER
timeframe (same key-level+IRL pattern re-forming in the same direction
while the original position is still live) are traded as ADDITIONAL
stacked positions, not skipped. Shown as routine in a real Gold example
(two stacked entries at the same open-close key level, both reaching 1:3;
one nearly stopped at breakeven first). Backtester/bot implication: risk
sizing must support multiple concurrent same-direction positions rather
than a strict one-trade-per-bias assumption. Not yet specified whether
stacking applies to origin trades too, or continuation setups only — open
question, watch for clarification in later videos.
- Extended runners are outliers, not the target: 1:6 seen in Video 10,
  1:7 seen in Video 14 — both explicitly called out as beyond the normal
  1:3 expectation, not something to calibrate default exits around.

## 7. Timeframes
- Bias/setup identification: higher timeframes (1H, 4H, sometimes 3H).
- Entry execution: drops to lower timeframes — 15-minute entries confirmed
  on the 5-minute chart.
- Uses both candlestick AND line charts — line chart specifically preferred
  for spotting clean liquidity sweeps / BOS (candlestick wicks can obscure
  it).
- **Holding-period nuance**: the overall directional BIAS can persist for
  weeks or months (set by weekly/monthly candle closes), but execution
  stays short-term — individual trades are still entered/exited on lower
  timeframes repeatedly in that direction, not held as one continuous
  multi-month position. Reconciles "I'm a day trader, I don't swing" with
  real examples of a bias holding for 2-3 months.

## 8. Session & Pair Rules (concrete, backtestable)
- Day trader — does not swing trades overnight as a rule.
- Avoid GBPUSD / EURUSD during Asian session (low "liquidity injection").
- Asian-session-appropriate pairs: AUDUSD, NZD pairs, USDCHF, GBPJPY, EURJPY.
- Each session (London/NY/Asia) has its own liquidity-injection window tied
  to real institutional order flow.
- Cancels pending limit orders that would only trigger outside London/NY for
  majors pairs.
- Avoid holding into very late hours — spread widens sharply around session
  rollover (~10pm reference).
- Data feed / broker reference: Oanda. Charting: TradingView (uses Replay
  mode for backtesting review).
- **News-event caveat** (from a real loss reviewed in Video 8): structural
  rules can get overridden short-term by major news releases (NFP
  specifically called out). Always confirm higher-timeframe trend context
  before entering, and treat news-day price action as elevated risk — the
  backtester should model/flag major news events rather than assume the
  rules hold unconditionally through them.
- **Soft heuristic on news direction** (Video 10, attributed to a past
  mentor, explicitly unverified by him personally): news-driven moves tend
  to go in the direction of the prevailing higher-timeframe bias, not
  against it. Treat as a secondary prior at most, not a core rule — doesn't
  contradict the news-event caveat above.
- **Cross-asset applicability claim** (Video 10, not independently
  verified): states the same framework applies to synthetic indices and
  crypto, not just forex/gold. Worth testing empirically per asset class
  rather than assuming it holds — market microstructure differs.

## 9. Open Questions / Expected in Later Videos
- Premium & discount pricing theory (hinted at end of Video 3 but not
  actually covered before the call ended — do not assume a later video
  covers it just because of numbering)
- The "10 trade rule" (confirmed to be prop-firm-challenge specific, still
  no precise definition)
- "QMR key level" — term used across Videos 7, 8, 12, and 13 without ever
  being defined; consistently used interchangeably with generic "key
  level" regardless of shape — treat as equivalent to "key level" unless a
  clearer definition surfaces
- "W Questions" (Bishop material) — unclear if Weekly-specific questions or
  a Who/What/When/Where/Why checklist
- A likely "Key Levels 2" video may exist (Video 11 ends mid-topic
  promising continuation same day) — not currently in our set of 18, watch
  for it if more material surfaces
- Trade stacking rules (Video 14): does stacking apply to origin trades,
  or continuation setups only? Not addressed yet.
- Remaining videos to process: 17-18 (course materials) plus the
  Web3Bish0p/Defi Bishop supplementary study videos and remaining 54 pages
  of the chart-examples PDF
