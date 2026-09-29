"""
The SLK system, in one place.

Not a variant of the shipped engine and not an A/B arm -- this is the
strategy as the course teaches it, assembled from
`knowledge-base/SLK_SPEC.md` after the full pass over both courses'
transcripts and frames. Backtest and live both read it from here so
they cannot drift apart.

Each entry names the rule and where it comes from. Anything not listed
keeps `run_backtest`'s own default, and that is deliberate: a setting
nobody can cite is not part of the system.

WHAT IS IN

  confirmation_triggers   The four Bishop enumerates, his two
                          highest-rated first. "If you ask me which
                          ones are likely best, personally I would tell
                          you these two ... if you have these two,
                          [missing it] is a missed entry"
                          (entries-part5 t=410-431). SLK_SPEC 5.1-5.5.

  erl_mode="target"       The target IS the external liquidity, not a
                          3R cap. Seven separate statements, no
                          counter-evidence; his own finished trades
                          read 3.4R to almost 7R, and none of those
                          numbers is one he chose. SLK_SPEC 7.

  bias_caveat=True        A Daily that only REJECTED still builds a
                          bias, provided the Weekly also rejected and
                          H4 carries the breakout. He trades this live
                          on XAUUSD and EURUSD. SLK_SPEC 1.

  liquidity_mode="both"   Single-candle and structural liquidity are
                          one pool seen at two zoom levels, not rival
                          definitions: "most times, your single candle
                          liquidity on your daily is going to be a
                          structural liquidity [on the lower
                          timeframe]" (bias-2 t=1140, and again at
                          bd2 t=825). SLK_SPEC 2.

WHAT IS OUT, AND WHY

  require_qmr             4th man plays QMR levels, but "I love to
  require_imbalance_      play..." is a preference, not a gate, and
  overlap                 Bishop -- the implementation authority, per
                          the operator's division of labour -- never
                          gates on either. Both are available as
                          variants in the runner. Calling a preference
                          a rule is how a system stops being the one
                          that was taught.

  the M45/M30/M15 ladder  In the source and deliberately scoped out:
                          "for now we can use only 1H" (operator,
                          2026-09-19).

NOT YET BUILT, so not here and not silently assumed away: origin vs
continuation as separate trades, the daily-only bias with a reduced
target, trendline liquidity, and the breakout candle's own extremes as
liquidity. SLK_SPEC section 8 rows 9-12.
"""

from __future__ import annotations

from ..engine.runner import TRIGGERS_TAUGHT
from .live_flags import LIVE_FIXED_FLAGS, LIVE_LAUNCH_FLAGS

SLK_SYSTEM = {
    "confirmation_triggers": TRIGGERS_TAUGHT,
    "erl_mode": "target",
    "bias_caveat": True,
}

# EMPTY, AND THAT IS THE RESULT OF A MEASUREMENT.
#
# This held seven settings until 2026-09-24. Measured against the plain
# reading above, on the same full history and the same three pairs:
#
#     plain taught    2063 trades   ~42% win   ~+0.9 R/trade  ~+1800R
#     plus my seven    212 trades   27.4% win   -0.08 R/trade    -17R
#
# The seven threw away NINETY PERCENT OF THE TRADES AND KEPT THE LOSING
# ONES. Not one of them was measured on its own before being switched
# on; they were assembled together and the stack was judged as a whole,
# which is how a system ends up worse than the thing it was meant to
# improve.
#
# What each one was, and whose idea it actually was:
#
#   liquidity_mode="both"       concept theirs (bias-2 t=1137, bd2
#                               t=825 -- single-candle and structural
#                               are one pool at two zoom levels), but
#                               "every candle, unbounded" was MINE.
#   daily_only_when_split       theirs, routine t=390-435.
#   require_imbalance_overlap   theirs, plug-and-play's two market
#                               conditions.
#   require_sponsored_level     condition theirs (t=869), but what
#                               counts as "sponsored" was mine.
#   first_presentation_only     the operator's, 2026-09-23.
#   trigger_priority            MINE. He rates two confirmations
#                               highest; he never says to pass on a
#                               weaker one that fires first.
#   require_flip_confirmation   MINE.
#
# Every mechanism survives in run_backtest, off by default, so each can
# be measured ON TOP of this baseline one at a time. Nothing returns
# here without a number showing it helps.
SLK_TAUGHT_OVERRIDES = {}

# Operational settings that are not strategy: the rollover-window skip
# and the 1R floor both came from live incidents and direct
# instructions, not from the course. Kept separate so nobody later
# reads them as taught rules.
SLK_OPERATIONAL = {
    **LIVE_FIXED_FLAGS,
    "origin_kind": LIVE_LAUNCH_FLAGS["origin_kind"],
    "close_based_sweep_break": LIVE_LAUNCH_FLAGS["close_based_sweep_break"],
    "stop_anchor": LIVE_LAUNCH_FLAGS["stop_anchor"],
}

# Available on top, one at a time, for the question "does this filter
# earn its place" -- never folded into SLK_SYSTEM.
SLK_VARIANTS = {
    "qmr": {"require_qmr": True},
    "imbalance": {"require_imbalance_overlap": True},

    # entry_fill="limit" -- MEASURED, EARNED ITS PLACE (2026-09-30).
    # SLK_SPEC 5.1/5.2: "entry is the return to it, not the engulfing
    # candle". The default fills AT the confirmation candle, which is
    # worse than the fill Bishop actually gets. Recent-year window
    # (2025-10-01 -> 2026-09-30), three pairs, same trade set:
    #     instant  n=90   42.2% win   +0.93 R/trade   PF 2.61
    #     limit    n=90   43.3% win   +1.01 R/trade   PF 2.79
    # Same trades, better fills -- strictly dominant, no trade count
    # lost. Kept as a variant rather than folded into SLK_SYSTEM so the
    # baseline stays reproducible; run_slk --variant limit is the
    # recommended arm until the operator promotes it.
    "limit": {"entry_fill": "limit"},
}


def slk_kwargs(**overrides) -> dict:
    """Everything `run_backtest` needs to run the system.

    Order is load-bearing: operational first, then the taught rules,
    then the deliberate overrides of an operational default. Merging
    SLK_OPERATIONAL last -- the original ordering -- would let
    LIVE_FIXED_FLAGS silently put the 1.0 reward floor back."""
    return {**SLK_OPERATIONAL, **SLK_SYSTEM, **SLK_TAUGHT_OVERRIDES, **overrides}
