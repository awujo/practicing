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
SLK_TAUGHT_OVERRIDES = {
    # The target IS the liquidity, so a setup whose liquidity sits close
    # by is not a small win -- it is a trade Bishop would not take. He
    # goes to the previous weekly high; he does not risk one to make one.
    #
    # The live floor is 1.0, set when the target was min(3R, ERL) and
    # could never be large. Pairing that floor with an uncapped target is
    # a combination nobody chose, and the 2026-09-23 live-windows run
    # shows what it cost -- 39% of all trades taken below 3R, and 67% of
    # the entire loss:
    #
    #     target    trades    net
    #     0-2R        1523   -337.1R
    #     2-3R         936   -204.5R
    #     8-12R        546    +60.4R
    #
    # It only means anything alongside min_stop_pips below. R is a ratio,
    # so on its own a reward floor prefers a TINY denominator -- which is
    # why raising it made the two instruments measured on 2026-09-23
    # worse, not better.
    "min_reward_r": 3.0,

    # The stop must be an invalidation zone, not a rounding error.
    # AUDJPY 2025-09-25 18:00 was entered at 97.930 with a stop at
    # 97.928 -- two tenths of a pip, on a cross whose spread is about
    # 1.5. It scored 125R against the reward floor and lost, as it
    # always would have.
    #
    # 2.0 is a judgement, not a citation, and is deliberately modest:
    # roughly one spread on a major, under one on a cross. Bishop never
    # gives a pip figure because he never needs one -- a real confirming
    # candle has a real wick. This declines the setups where it does not
    # rather than inventing a wider stop for them.
    "min_stop_pips": 2.0,

    # Take the setup the FIRST time price presents it, and only then.
    #
    # Operator, 2026-09-23, after reading a rendered chart: "it's not
    # about putting a boundary, a cage around it. It's about using it
    # the first time it presented itself... if you use it the first
    # time it presented itself it will not take long."
    #
    # That is the whole answer to the two gaps the charts exposed --
    # breakout-to-pool running to 180 bars, and the engine watching
    # confirmations go past before taking a late one. Both came from
    # rules that went looking for a SECOND chance: every 4H candle in
    # the leg as its own setup, and MAX_CANDIDATES_PER_SETUP=3 letting
    # a rejected first confirmation fall through. Neither is a window
    # that was too wide.
    #
    # Unlike min_stop_pips this needs no number, which is why it is the
    # better fix: there is nothing to tune and nothing to be late for.
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
