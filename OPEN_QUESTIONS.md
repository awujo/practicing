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
grading is timeframe-relative, not absolute) or something else.

**Backtested, 2026-08-28** (GitHub Actions, `compare-confirmation-sources.yml`,
now reverted — see commit `51d6695` / revert `3495246`): ran the current
swing-fractal "breakout" definition against a "most recent A/V key
level" alternate, both entry styles, all 25 instruments, every trade
entered 2025-01-01 onward, same data snapshot for both. Current
definition won clearly: **+2,688.7R vs +2,311.7R** (2,528 vs 2,324
trades, 53.4% vs 51.6% win rate) — key-level only came out ahead on 11
of 50 instrument/style combinations, and lost badly on several
(GBPCHF aggressive: −58R). On JP225 itself, the case that raised this:
conservative favored the current definition (+31.3R vs +20.6R),
aggressive favored key-level (+60.0R vs +44.0R) — mixed even there.

Combined with Video 17's sourced rule already in the code (key-level
disrespects are entry triggers, not bias-flip signals), two independent
reasons now point the same way. Decision: **leave the live bot as-is.**
Still open only if the specific Bishop video/example turns up and says
otherwise — the empirical result would need re-running against whatever
that reading actually specifies, since "most recent key level" was one
specific implementation of "most recent breakout," not the only
possible one.

## Technical

*(none open right now — the lookahead-bias item that lived here is
fixed, measured, and moved to `PROJECT_HISTORY.md`'s "Phase 6" entry.
Add new ones here as they come up.)*
