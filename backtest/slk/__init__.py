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
"""
