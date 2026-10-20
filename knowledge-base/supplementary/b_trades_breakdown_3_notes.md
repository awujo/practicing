# Bishop Supplementary: "Trades Breakdown 3"

## Content type
A weekly real-trade breakdown across (per the visual pass below) 7 pairs
— GBPCAD, AUDCHF, NZDCHF, USDJPY, GBPUSD ("GU"), USDCHF, USDCAD — though
Bishop verbally frames it as "6 trades this week" at the start (NZDCHF is
a genuine 7th pair present in the video, introduced with only a terse
"same idea" and no pair name spoken aloud, so it's easy to undercount by
ear alone — resolved here only because the on-screen ticker was checked
directly). Overwhelmingly reinforcement of the already-documented
cascade, with one clarifying nuance on stop-loss placement and one
explicit statement of Bishop's timeframe-hierarchy preference rule.

## Reinforced: prefer a HIGHER lower-timeframe confirmation over a lower
one when both present a valid signal simultaneously (explicit rule)
On GBPCAD, both a 2H and a 1H breakout appeared at the same time. Bishop
explicitly chose the 2H over the 1H, stating the reasoning directly:
"in time frame hierarchy... your four hour is higher than your three,
two and the rest of them... I believe that price can just come into the
two hour level and then buy without ever coming to the one hour because
the two hour is actually stronger than the one hour in terms of
hierarchy." This is a genuinely explicit tie-breaking rule for Section
7's "confirmation timeframe is flexible" note: when multiple lower
timeframes present a valid confirmation trigger concurrently, prefer the
HIGHEST (strongest) one available rather than the first one chronologically
or the lowest one. Backtester implication: when scanning a candidate set
of confirmation timeframes (e.g. 30min/1H/2H/3H/4H), and more than one
produces a valid signal at the same decision point, rank by timeframe
strength (higher wins) rather than picking arbitrarily or defaulting to
the lowest.

## Reinforced: stop-loss placement should clear BOTH the confirming
key level AND any nearby liquidity, not just the entry candle
On the GBPUSD trade, Bishop explicitly did not place his stop immediately
behind the engulfing/entry candle, because "price has every right to come
to this liquidity" first before continuing — and price later did exactly
that, running back to sweep the nearby liquidity and stopping out traders
who used a tighter stop, before ultimately reversing in the intended
direction. Explicit rule stated: "I just like to keep my stop loss above
liquidities and key levels too." Refines/extends the existing stop-
placement guidance (Video 13, and the Daily Routine video's near-miss
example) with a slightly more general framing: the stop should clear not
just the immediate invalidation candle but any known nearby liquidity
pool the market has "every right" to sweep first as a normal continuation
move, not just as a reversal signal.

## Reconfirmed
- Full cascade (weekly/daily bias -> 4H breakout -> single candle
  liquidity -> rejection -> confirmation entry) reconfirmed across all 7
  pairs.
- "After external liquidity is taken, expect a reversal" restated again,
  with a real near-instant example (USDCAD: "the reversal was
  instantaneous").
- Confirmation entries taken across a wide spread of lower timeframes
  again (30min, 1H, 2H) — further reinforcing Section 7's flexible-
  confirmation-timeframe note, now with the explicit tie-break rule
  above layered on top.
- Explicit honest admission of a loss (AUDCHF, engulfing confirmation
  entry) with no excuse-making — "I took the loss and moved on" —
  consistent with prior risk-management honesty notes.
- Explicit statement that a bearish 4H breakout counter to an established
  bullish structure does NOT itself invalidate the bullish bias (USDCAD
  example) — consistent with Video 16/17's bias-flip state machine
  requiring more than a single counter-move to actually flip bias.
- "There's always tomorrow" restated verbatim from the Bias & Entries
  video's risk-management framing.

## Visual verification pass
Re-transcribed via `transcribe.yml` (video_slug `bishop-trades-
breakdown-3`, source: the `defi-bishop` GitHub release) and verified
with 10s-interval frame extraction across all 6 named trade windows plus
the extra unnamed NZDCHF segment, read directly, cross-referenced against
the TradingView symbol sidebar in-frame (a stable 7-pair watchlist:
GBPCAD, AUDCHF, NZDCHF, USDJPY, GBPUSD, USDCHF, USDCAD — confirming the
7th pair is real, not a window-boundary artifact). Both "JVP card" and
"GDP card" audio garbles are unambiguously **GBPCAD**; "GU" is confirmed
as trader shorthand for **GBPUSD**. Confirms real, concretely-marked
levels and trade tools behind every trade, not just narration: GBPCAD
daily ray ~1.85800 and a 1H chart with a circled entry candle at ~1.86000
inside a drawn green/red risk-reward box (~1.86100-1.87100 target zone);
AUDCHF daily, unmarked at the frame reviewed; NZDCHF 1H choppy
consolidation around ~0.46250-0.46500; USDJPY 1H ray ~160.280; GBPUSD 4H
with a drawn risk-reward box (resistance ~1.33925, target ~1.33450);
USDCHF 4H ray ~0.79750; USDCAD 4H — an actual TradingView Risk/Reward
drawing tool with printed numbers ("Risk/reward ratio: 5.04", "Stop:
0.00111 / 11.1 pips"), the clearest concrete confirmation yet that these
are real position-sizing tools, not just retrospective narration. No
corrections needed to the mechanical/risk-management claims — only the
pair-count clarification (7 vs. the spoken "6") noted above.

## Open items
- No new terminology beyond the timeframe-hierarchy tie-break rule and
  the liquidity-clearing stop-placement nuance documented above.
