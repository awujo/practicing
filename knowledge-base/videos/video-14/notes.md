# Video 14: Entry Models 1

## Content type
Direct follow-up to Video 13's decision tree, reframed as an enumerated set
of confirmation-entry "patterns" plus two real Gold trade walkthroughs that
introduce **trade stacking**. Also gives the clearest direct win-rate quote
for the continuation setup so far.

## Explicit win-rate statement (direct quote, matches Video 11's number)
"I said something in the group... this continuation setup has over like a
70% to 80% win rate." Same figure as Video 11's quantified 70-80% pattern-
occurrence frequency, now stated directly as a win-rate claim rather than a
pattern-occurrence frequency — treat both as the same underlying number
applied to two framings (setup reliability vs. win rate), not two separate
data points.

## THREE CONFIRMATION-ENTRY PATTERNS (post-IRL, post-key-level-tap)
After IRL is taken and price plays out from a key level overlapping an
imbalance, the confirmation entry takes one of three forms:

1. **Direct mitigation**: price engulfs -> directly mitigates/plays the
   newly-created A-shape/V-shape key level -> continues in the anticipated
   direction. (Matches Video 13 Branch 1/3 — clean or IRL-optional
   continuation.)
2. **Engulf + open-close break, return to open-close**: price engulfs AND
   also breaks an open-close level (formed by the 2 candles immediately
   before the engulfing) -> expect price to return specifically to that
   broken open-close and continue from there, not the original A/V-shape
   extreme. (Matches Video 13 Branch 4 — nested disrespected open-close,
   prefer the closer/newer level — this is the same rule restated as a
   pattern rather than a probability.)
3. **Fresh IRL required after engulf**: price engulfs -> the next lower-
   timeframe candle trades close to but does NOT tap the resulting V/A-shape
   key level -> that next candle itself becomes fresh IRL -> must be swept
   -> then the key level plays out -> continue. (Matches Video 13 Branch 2 —
   slow grind, fresh IRL propagates down a timeframe.)

**Reconciliation with Video 13's 4-branch tree**: these three patterns are
the same underlying mechanics as Video 13's branches, described from the
"what do I actually see on my execution timeframe" angle rather than the
"probability tree" angle. No new mechanics — treat Video 13 as the
probability-annotated version and Video 14 as the pattern-recognition
checklist version of the identical logic. For implementation: a single
decision function can serve both; Video 13 supplies the ~70% weighting for
choosing pattern 2 over the alternative when both a fresh open-close AND
the original extreme are viable targets.

## TRADE STACKING (new concept)
Once a continuation trade is open and further qualifying conditions appear
on a LOWER timeframe (i.e. a fresh instance of the same key-level+IRL setup
forms in the same direction while the original trade is still running),
add an additional position on top of the original. Described as routine,
not exceptional — happened twice in the Gold walkthrough below. Implication
for the bot: position sizing/risk must account for multiple concurrently
open, same-direction stacked trades rather than assuming one position per
bias read.

## Real trade walkthroughs (Gold/XAUUSD)

### Walkthrough 1 — two stacked entries
- First entry taken off the standard continuation setup.
- Price returned to the SAME open-close key level a second time -> second
  (stacked) entry taken at that same level.
- Both entries reportedly reached 1:3.
- One of the two nearly got stopped out at breakeven first (stop had been
  moved to breakeven, price wicked back near it) before continuing to
  target — explicit acknowledgment that breakeven-stop trades can still
  feel uncomfortable/nearly fail even when they ultimately work.

### Walkthrough 2 — extended runner
- Separate Gold example, single entry, ran to **1:7** — an outlier result
  explicitly called out as beyond the usual 1:3 target, not the expectation.

## Reconfirmed
- 1:3 remains the standard/expected target; extended runners (1:6 in Video
  10, 1:7 here) are explicitly framed as upside outliers, not the norm —
  don't calibrate default backtest exits to the outlier cases.
- Gold (XAUUSD) reconfirmed as an actively traded instrument under this
  same framework, not just forex pairs.

## Open items
- No new open questions introduced. Trade stacking is a new mechanic to
  fold into Section 6 (Trade Management) — needs explicit rules once more
  examples are seen (e.g., does stacking apply only to continuation setups,
  or also origin trades? Not addressed here.).
