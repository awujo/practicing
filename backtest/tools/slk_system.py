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
                          (entries-part5 t=420-435). SLK_SPEC 5.1-5.5.

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
    "liquidity_mode": "both",
}

# Settings where the TAUGHT system deliberately departs from a live
# default. Its own bundle, because it is neither a pure course rule
# (SLK_SYSTEM) nor a deployment setting (SLK_OPERATIONAL) -- it is a
# live setting the course overrules, and collapsing it into either one
# would lose that. Nobody reading SLK_SYSTEM should be able to cite the
# course for a number the bots chose, and nobody reading
# SLK_OPERATIONAL should think this one is still in force.
# Settings where the TAUGHT system deliberately departs from a live
# default. Its own bundle, because it is neither a pure course rule
# (SLK_SYSTEM) nor a deployment setting (SLK_OPERATIONAL) -- it is a
# live setting the course overrules, and collapsing it into either one
# would lose that.
#
# NOTHING HERE MAY BE A NUMBER I CHOSE. Two were, and both are gone:
#
#   min_stop_pips = 2.0   Mine. Operator, 2026-09-23: "I invented that
#                         number -- what the heck is this guy. Is this
#                         what you were taught?" No, it is not. It was
#                         put there to stop 0.2-pip stops, which are a
#                         real problem, but a filter nobody taught is
#                         not a fix -- it is me overruling the course
#                         with a guess. The honest treatment is already
#                         in place: postmortem charges spread as
#                         spread_pips/risk_pips, so a 0.2-pip stop
#                         shows up costing 7.5R instead of being
#                         quietly excluded. Let the cost be visible
#                         rather than hiding the trade.
#
#   min_reward_r = 3.0    Also mine, and the operator did not even have
#                         to point at it. I justified it with a loss
#                         table, but erl_mode="target" means the target
#                         IS the liquidity at whatever distance it
#                         sits, so a 1.5R run to the previous weekly
#                         high is a trade the course takes. The 1.0
#                         floor in LIVE_FIXED_FLAGS stays, because that
#                         one IS sourced -- "a trade of less than 1R
#                         doesn't make sense to hold" (2026-09-01).
#
# Both mechanisms remain in run_backtest, off by default, so the
# question can be MEASURED later. Neither is part of the system.
SLK_TAUGHT_OVERRIDES = {
    "first_presentation_only": True,

    # Rank the confirmations, do not race them.
    #
    # "If you ask me which ones are likely best, personally I would tell
    # you these two ... if you have these two, [missing it] is a missed
    # entry" (entries-part5 t=420-435) -- breakout and sweep+break. On
    # eight instruments the engine produced disrespect 74% of trades
    # against breakout 2% and sweep_break 1%, the exact inverse.
    #
    # Not a scoring system and not a preference of mine: the triggers
    # simply cannot form at the same speed. disrespect can fire the
    # candle after the touch; a breakout needs a low, a lift and a close
    # beyond it. So the earliest always won and the ordering in
    # confirmation_triggers only ever broke ties inside one candle.
    "trigger_priority": True,
}

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
}


def slk_kwargs(**overrides) -> dict:
    """Everything `run_backtest` needs to run the system.

    Order is load-bearing: operational first, then the taught rules,
    then the deliberate overrides of an operational default. Merging
    SLK_OPERATIONAL last -- the original ordering -- would let
    LIVE_FIXED_FLAGS silently put the 1.0 reward floor back."""
    return {**SLK_OPERATIONAL, **SLK_SYSTEM, **SLK_TAUGHT_OVERRIDES, **overrides}
