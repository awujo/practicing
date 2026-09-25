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
    sweep       the L: liquidity taken, and the nearest key level to it
    confirmation the H1 open-close level, engulfed, then returned to
    liquidity   external range liquidity, as the target
    orders      one resting order per level, newest confirmation wins
    replay      the driver that walks H1 forward and does all of it

WHAT IS STILL NOT BUILT, listed so it cannot be mistaken for finished:

    the Weekly is loaded but only reaches the target search; the course
    builds bias from it downward, and here bias starts at the Daily

    four of the five confirmation forms -- direct mitigation (video-14
    5.1), inducement (5.3), Bishop's breakout (5.4) and sweep-and-break
    (5.5). Only the open-close engulf (5.2) is in. These ADD entries, so
    every number this package produces is a floor, not an estimate

    the polarity flip is detected and honoured as an ending, but a
    flipped level is never traded the other way
"""
