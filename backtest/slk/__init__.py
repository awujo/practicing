"""
SLK as taught, written from the source rather than grown from the old
engine.

This package exists because `backtest/engine/` carries vocabulary that
is mine, not the course's -- "conservative" and "aggressive" entry
styles, "engulfing" meaning a candlestick pattern -- and every attempt
to express a taught rule inside it went through one of those names
first. The operator, 2026-09-25:

    "Was there anything like conservative and aggressive in what they
     taught? ... Is it hard to just model what was taught?"

No, and no. So nothing in here is named for anything except what the
course calls it, and no rule enters without a quote.

Two hard constraints, both of which the old engine broke repeatedly:

  NO FUTURE        Every function takes the candles up to NOW and
                   nothing after. Not a filter that remembers to bound
                   itself -- an argument that cannot contain tomorrow.

  NO INVENTED      No pip thresholds, no scores, no ratios that nobody
  NUMBERS          said out loud. If the source does not give a number,
                   the rule is expressed structurally or it is not
                   built.

The modules, in the order the cascade uses them:

    levels      the four key-level shapes, and the polarity flip
    stream      those levels as they confirm, one candle at a time
    bias        rejection, closure, breakout on the next timeframe down
    cascade     both bias routes on both rungs, answered in O(1)
    sweep       the L: liquidity taken, the nearest key level to it, and
                the Weekly's contribution to bias
    confirmation the H1 open-close level, engulfed, then returned to
    entries     the other forms: inducement, breakout, sweep-and-break
    liquidity   external range liquidity, as the target
    orders      one resting order per level, newest confirmation wins
    replay      the driver that walks H1 forward and does all of it

WHAT IS STILL NOT BUILT, listed so it cannot be mistaken for finished:

    4th man's direct mitigation (5.1) is not a separate order. On a line
    chart it is the SAME event as the open-close engulf at a shallower
    depth, and the operator specified the deeper one in their own words.
    The shallow depth is recorded on every engulf order so it can be
    measured; entries.py sets out the reasoning in full

    the entry timeframe is H1 only. The source's own ladder reaches M5
    (part5 frames, "H3/H2/H1/M45/M30/M5"), and the operator scoped it on
    2026-09-19: "for now we can use only 1H". A known lever, not a gap

    a flipped key level is only traded the other way inside a reaction
    (entries.ReactionWatch); the level stream itself still drops a
    disrespected level rather than flipping it

    spread and slippage. The reporting layer charges spread per trade
    against that trade's own risk, which is honest arithmetic applied
    afterwards rather than a fill simulation
"""
