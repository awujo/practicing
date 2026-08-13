# Bishop Supplementary: "20min Part 1 - Repeating System"

## Content type
Bishop's most explicit personal-system walkthrough yet: states directly
that SLK admits many valid personal approaches ("that's why we have a lot
of SLK traders, they all have their own way") and then documents his own
in detail across 8 real trades (US30, USDCHF, AUDCAD, USDCAD, USOIL,
AUDUSD, AUDJPY, EURAUD). Explicitly attributes the ABC->XYZ framing
directly to "my mentor," which is a nice direct confirmation that Video
12's IF-THEN pseudocode language is literally the mentor's own phrase,
not just Video 12's own paraphrase. Mostly reinforcement, with two
genuinely new, valuable refinements.

## NEW: Liquidity is not always single-candle — can be multi-candle
"structural liquidity" (extends Video 18's SCF concept)
Bishop explicitly qualifies his own "single candle liquidity" preference:
"it's not all the time your form of liquidity is going to be a single
candle. Sometimes it can be more than one candle... a series of
candles... also going to be like structural liquidity." Describes a
broader structural high/low spanning MULTIPLE candles (an "advanced
market structure" swing point) filling the same functional role as a
Single Candle Formation — a liquidity point that must be swept before
the nearby key level plays out — just without being reducible to one
candle's high/low.
- **Refines Section 3's SCF concept**: single-candle liquidity is the
  SIMPLEST/most common case, not the ONLY case. The underlying functional
  role (a liquidity pool near a key level, swept before the reaction)
  should be detected more generally as "the nearest prior local
  extreme(s) forming a structural swing point," of which a single candle
  is a special case (a swing point of width 1).
- **Backtester implication**: liquidity-pool detection should not be
  hard-coded to single-candle extremes only — needs to also detect
  multi-candle structural swing highs/lows as valid liquidity references.

## NEW: Imbalance-fill priority can override nearest-liquidity preference
Bishop explicitly and repeatedly observes (multiple real trades: AUDUSD,
AUDJPY, EURAUD) that price sometimes SKIPS the nearest single-candle/
structural liquidity and continues to a MORE DISTANT level instead,
because a larger fair-value-gap imbalance needs to be filled at that
farther point first: "it's something I've seen over time whereby price
tends to pull into a higher level to feel that imbalance." Stated as a
recurring empirical pattern, not a one-off.
- **Refines Section 5's key-level ranking logic**: adds a FOURTH ranking
  factor alongside imbalance-overlap (quality signal), recency/proximity
  (disrespected-level priority), and prior-test-count (QMR) — the
  presence of a larger unfilled imbalance at a more distant level can
  pull price PAST the nearer liquidity/key level entirely. Practical
  guidance given: when both a near and a far candidate level exist, and
  the far one has a larger/more obvious imbalance needing to be filled,
  don't assume the near one will be used — wait to see which one price
  actually taps before committing to an entry.
- Directly demonstrated multiple times: price by-passing the immediate
  next candle's liquidity and continuing to a further engulfed open-close
  or extreme key level instead, explicitly because of this dynamic.

## Reinforced: "Don't marry a bias — it can flip at any point" (discipline
principle, complements the mechanical bias-flip state machine)
Real trade example (a pair with a multi-week bearish bias that suddenly
gave a genuine bullish break of structure): explicit statement "you don't
have to marry a bias. A bias can flip at any point in time." This is the
PSYCHOLOGICAL/discipline complement to Video 16/17's mechanical bias-flip
state machine (Section 2) — once the state-machine conditions for a flip
are actually met, act on the new bias immediately and fully, rather than
staying anchored to the prior one out of inertia. Not a new mechanical
rule, but a useful explicit discipline note worth preserving alongside
the state machine itself.

## Reinforced: hard "no trade until rejection" patience rule
Stated with unusual bluntness: "my system says wait for a rejection...
until you see that rejection there is no trade for you." Direct
restatement of Section 5B's "requires patience, do not force it before
inducement forms," now phrased as an absolute (no conditional entries
before the rejection confirms, regardless of how confident the setup
looks beforehand).

## Reconfirmed
- The ABC->XYZ IF-THEN framing is confirmed to be a DIRECT QUOTE from the
  mentor himself ("my mentor says you want to see ABC then you do XYZ"),
  not just Video 12's own paraphrase — strengthens confidence that this
  pseudocode-style framing is core, canonical mentor terminology.
- Confirmation entry taken across an even wider range of lower
  timeframes in this video's trades: 15min, 30min, 45min, 1H, 2H, 3H —
  further reinforcing the "confirmation timeframe is flexible" note
  already added to Section 7.
- "Single candle liquidity," "daily reject daily," and the general
  weekly->daily->4H->confirmation cascade all reconfirmed yet again
  across 8 more real trades.
- Explicit honesty about a trade that would have stopped out on its
  first rejection attempt before later working on a second attempt —
  "it doesn't mean your bias was wrong," consistent with prior
  risk-management honesty notes.

## Open items
- No new terminology. 2 of 6 Bishop videos remain to be processed
  (trades_breakdown, what_next).
