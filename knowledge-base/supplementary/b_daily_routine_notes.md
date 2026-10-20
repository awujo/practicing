# Bishop Supplementary: "Daily Routine & Trade Breakdown"

## Content type
A full weekly operational walkthrough across 9 pairs (USDCHF, AUDUSD,
USDCAD, USDJPY, XAUUSD, AUDCAD, CADCHF, EURNZD, UK100 — corrected/
confirmed by the visual pass below), showing
Bishop's actual daily scanning routine plus real trade outcomes —
several wins, several honest misses, one stop-out. Mostly operational/
process content layered on top of the already-documented mechanics
(weekly->daily->4H alignment, breakout, single candle liquidity,
confirmation entry), but introduces a genuinely useful multi-pair
scanning workflow and several honest risk-management data points.

## NEW: Multi-pair scanning workflow (operational, worth encoding in bot
architecture)
Explicit trade-off disclosure for trading many pairs simultaneously:
- **Pro**: more setups/opportunities.
- **Cons** (stated directly, not hypothetical): (1) higher AGGREGATE risk
  exposure across concurrently-monitored/open positions than trading
  fewer pairs, (2) real risk of missing or forgetting flagged setups
  simply due to volume, (3) mentally "draining"/"strenuous" to analyze
  many pairs consistently.
- **Workflow**: maintain a personal **checklist** (explicit criteria for
  what to look for before considering a pair) and a **flagging system** —
  a pair moves through informal states: unflagged -> "flagged" (partial
  criteria met, e.g. daily confirms bias but 4H hasn't yet) -> confirmed
  setup -> entry taken, OR flagged-but-never-triggered (a "miss").
  Flagged pairs get periodically re-checked rather than continuously
  monitored.
- **Cadence**: wake ~5-6am, full scan of all tracked pairs by 7am
  (~15-30 min total), periodic re-checks of flagged pairs through the
  day, final check before sleep (~11pm-12am).
- **Backtester/bot implication**: this maps directly onto a per-pair
  state-machine watchlist architecture — track each pair's current
  cascade state (bias direction, which timeframes have confirmed, which
  haven't yet) rather than a purely reactive per-candle scan. Useful
  design pattern independent of whether the bot runs on a human cadence.

## Reinforced: strict higher-timeframe-bias discipline (concrete examples)
Repeatedly demonstrates actively DISREGARDING lower-timeframe signals
that contradict the established higher-timeframe bias, not just
weighting them less — e.g., explicitly ignoring bullish breakouts on 4H
while the weekly/daily bias is bearish ("in a bearish condition there's
going to be bullish breakouts [sometimes], I'm not interested in this
guy"). Consistent with Section 2's Daily-beats-4H priority rule, but adds
the operational discipline point: don't just discount conflicting
lower-timeframe signals, actively skip acting on them entirely while the
higher-timeframe bias holds.

## NEW: Confirmation-entry timeframe is genuinely flexible, not fixed
Across the pairs discussed, confirmation entries were taken variously off
a **30-minute engulfing**, a **1-hour breakout**, a **2-hour breakout**,
and a **3-hour breakout** — whichever lower timeframe happened to present
a clean signal first, not a single fixed confirmation timeframe. Refines
Section 7's timeframe guidance: the confirmation-entry step should scan
across a small set of candidate lower timeframes (e.g. 30min/1H/2H/3H)
rather than assuming one canonical confirmation TF — consistent with, and
extending, Video 15's "4H specifically emphasized for bias, but execution
timeframe flexible" framing.

## Real risk-management data points (honest, not cherry-picked)
- Multiple flagged setups where price never returned to the level at all
  ("price never came back there") — explicitly normalized: "that's one
  of the risks... you'll miss good setups as well." Reinforces the
  probabilistic, non-deterministic framing already in STRATEGY.md.
- One real near-stop-out example (USDJPY): if the stop had been placed
  too tight/close to the literal entry point, price would have "sniped"
  it before the real move; a stop placed slightly further out (behind
  the real invalidation point) would have survived. Reinforces Video 13's
  mechanized stop-loss judgment nuance (prefer the safer/more distant
  invalidation point over the tightest possible placement in ambiguous
  cases).
- Real winning trades with concrete outcomes: one graded ~5R, another
  ~5.5-5.6R — consistent with Section 6's framing that extended runners
  (beyond the standard 1:3) are good-but-outlier outcomes, not the norm
  to plan around.
- Explicit acknowledgment that sometimes there's genuinely "no clear
  intel for sales, no clear intel for buys" and the only thing to do is
  "stick to what you believe is going to play out" — an honest admission
  that not every situation cleanly resolves via the ruleset; some
  discretion/judgment remains even within a mostly mechanized system.

## Reconfirmed
- "Single [candle] liquidity" (Bishop's SCF term) used constantly across
  every pair breakdown — further reconfirmation of Video 18's Single
  Candle Formation concept, now the 3rd independent confirmation across
  Bishop's material.
- "H4 reject H4" used as Bishop's own shorthand label for a 4H candle
  rejecting from a 4H key level — same naming pattern as the mentor's
  "daily reject daily" (Section 2), just applied one timeframe down.
- Confirmation entry can be breakout, engulfing, OR sweep+break —
  reconfirmed yet again, now across more timeframe variants (see above).
- Multiple valid nested key levels can exist simultaneously as candidates
  (echoes Section 5's QM/QMR and disrespected-level-priority material) —
  no new resolution mechanism given here beyond what's already
  documented.

## Visual verification pass
Re-transcribed via `transcribe.yml` (video_slug `bishop-daily-routine`,
source: the `defi-bishop` GitHub release) and verified with 10s-interval
frame extraction across both scanning passes (initial flag pass +
follow-up entry pass) for every pair, read directly, cross-referenced
against the TradingView symbol sidebar visible throughout (a stable
9-pair watchlist: XAUUSD, EURNZD, USDCHF, AUDUSD, USDCAD, USDJPY, UK100,
AUDCAD, CADCHF). **Corrections to the Content type list above**:
"CADJPY" is unambiguously **CADCHF** on-screen (audio garbles it as "car
theater"); the passing "check g you" audio reference is casual shorthand
for GBPUSD but it is NOT part of the actual tracked watchlist for this
session (never appears in the sidebar and gets no real breakdown) — it
has been dropped from the pair count, correcting "~10 pairs" to the
actual 9. Confirms real, concretely-marked levels/trade zones behind
every pair: USDCHF daily ray ~0.80300; AUDUSD daily ray ~0.69600; USDJPY
daily rays ~163,000/~161,000 and a 2H entry ray ~162.400 (the near-stop-
out example); XAUUSD 4H rays ~4,200/~4,080; UK100 daily rays
~10,760/~10,440 and, in the follow-up pass, a literal drawn green/red
risk-reward box on the 3H chart around the ~10,530-10,585 entry (a real
marked trade zone, not just narration); AUDCAD 4H rays ~0.98450/~0.98400
with a drawn triangular "V shape key level with a body" annotation
matching the transcript's own description; CADCHF weekly/4H rays
~0.57700/~0.57050/~0.57000; EURNZD 4H rays ~2.00500/~1.98500/~1.94000,
with an on-screen chart title reading "ROUTINE x BREAKDOWN" confirming
the video's own content framing. No corrections needed to the mechanical/
workflow/risk-management claims — only the two pair-identification
issues above.

## Open items
- No new terminology beyond the multi-pair scanning workflow and
  flexible-confirmation-timeframe notes already documented above. All
  Bishop supplementary videos originally planned, plus the newer
  multi-video release batch, have now been visually verified.
