# Video 5: Liquidity Types n Forms

## Content type
Systematic teaching session on the two "types" of liquidity (IRL/ERL) and the "forms" of liquidity (daily/weekly/monthly/Asian highs-lows, trendline). Mostly reconfirms and refines earlier videos (4/6), with two genuinely new/clarified pieces.

## Explicit exclusions (useful — tells us what NOT to implement)
- States he no longer uses **double top / double bottom** pattern recognition — deliberately simplified away from it.
- Reconfirms (from Video 1) he does NOT use "central bank dealer's range" concepts. The system is intentionally minimal: structure + liquidity + key level only.

## Trendline liquidity — "magnet" mechanism (refined explanation)
- When a counter-trend retracement creates a sequence of consecutive higher-lows (or lower-highs), that sequence becomes **trendline liquidity** that acts as a **magnet** — price is drawn back to take it out before the main trend resumes.
- He explicitly does NOT draw the trendline on his chart. Instead he uses **"the last resort"** — the final/most recent point in that sequence, closest to his key level — as the actual reference point, rather than tracking the whole line.
- Direct causal explanation for why inducement liquidity is wanted near entries: clearing the magnet zone is exactly what makes "momentum kick in all of a sudden" after entry.

## Sequential liquidity rule (clean, directly implementable algorithm)
The clearest statement yet of an alternating-target rule per timeframe category:
- Previous daily high taken -> next target is previous daily low (and vice versa).
- Previous weekly high taken -> next target is previous weekly low (and vice versa).
- Previous monthly high taken -> next target is previous monthly low (and vice versa).
- Asian low taken -> next target is Asian high (and vice versa).
This is a simple bidirectional pendulum per timeframe-category: once one side of a given timeframe's liquidity is taken, the target flips to the opposite side of that SAME category — directly codeable as a state machine.

## Dual-purpose confirmation
Previous daily/weekly/monthly highs/lows can be used both to **frame a bias** (entry direction) AND as **exit reference points** — same dual-purpose principle already noted for key levels in Video 9, now extended explicitly to these liquidity forms too.

## Open items
No new open questions. Confirms Video 9's point that these liquidity forms are the raw inputs later assembled into the top-down storyline/bias process.
