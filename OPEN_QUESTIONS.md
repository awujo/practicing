# Open questions

Things that came up during development or live operation that aren't
resolved yet — either because they need a source check against the
Bishop material that hasn't been done, or because they need a decision
from Tobi before any code changes. Add to this file instead of letting
a question get dropped mid-conversation. Move an entry to
`PROJECT_HISTORY.md` (or `bot/OPERATIONS_LOG.md` for live-ops items)
once it's actually resolved, with the commit/decision that closed it.

Format per entry: what's unresolved, why it matters, what's needed to
close it out.

## Strategy

### "Most recent breakout" — is the reference level always the major swing (ERL), or can it be a nearer local/key-level break?

**Raised**: 2026-08-28, live JP225 Daily read.

`detect_confirmations()` (`backtest/engine/bias.py`) treats a "breakout"
as a close beyond the last **n=2 fractal swing high/low** — which, per
STRATEGY.md's own definition, aims at the external range liquidity
(ERL) / major prior extreme. On 2026-08-28, JP225's Daily rallied hard
(Aug 26 close 67,080) and disrespected a nearby A-shape key level at
66,183 — but the code's fractal-swing reference level was still all the
way up at 68,649 (Aug 14), so no new "breakout" confirmation fired and
the Daily storyline stayed bearish.

Checked STRATEGY.md (Video 16/17/18 sections) and the code's own
sourced comments: both currently agree that key-level (A/V-shape)
disrespects are Section 5 **entry triggers**, not Section 2
breakout/bias-flip signals — so as coded today, this was not a bug.
But the underlying question — whether Bishop's own "most recent
breakout" examples ever use a smaller/nearer swing than the governing
major extreme — was not resolved; Tobi pointed at a specific live
example (JP225 Daily) that reads, by eye, as a breakout, and asked to
check the videos, but we didn't land on which video/timestamp to check
against before the thread was dropped.

**To close this out**: find the specific Bishop video/example (Tobi may
remember it) where "most recent breakout" is called on a level nearer
than the prior major swing extreme, and check whether that reference
level is itself just a smaller-timeframe major extreme (i.e. the
grading is timeframe-relative, not absolute) or something else. If the
nearer-level reading holds up, `detect_confirmations()`'s swing-high/low
detection needs to change (and per Tobi's 2026-08-28 request, that
change should be backtested against the current fractal-swing logic
across all instruments — via GitHub Actions, not locally — before it
touches the live bot).

## Technical

*(none logged yet — add here as they come up)*
