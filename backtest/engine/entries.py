"""
Entry triggers -- STRATEGY.md Section 5.

Six pieces:

1. `is_engulfing()` -- standard engulfing-candle detection. Section 5:
   "An engulfing candle consuming one/both of [a V/A-shape's candles] is
   functionally equivalent to a body-close break of a V/A-shape level."

2. `fourth_man_confirmation_level()` -- "4th man confirmation": a distinct
   confirmation-entry trigger, NOT in the transcribed knowledge base --
   real name Bishop's own students use for it, confirmed directly by the
   user. A 2-candle liquidity-sweep-and-reclaim: `curr` sweeps `prev`'s
   liquidity on one side, closes back INTO `prev`'s range, while `prev`'s
   OTHER side stays untouched ("still standing") -- e.g. bullish: curr's
   low sweeps below prev's low, curr closes back above prev's low, and
   prev's high is never touched by curr. That reclaim pattern itself IS
   treated as forming a V-shape (bullish) or A-shape (bearish) key level
   -- same "V"/"A" shape labels and closing-price convention key_levels.py
   already uses, and the same "2 candles in, one KeyLevel out" shape as
   `detect_open_close_level()` -- usable directly as the entry trigger, or
   as one of a level's SELECTION candidates. Preferred on 1H/2H per direct
   user guidance ("I prefer it on 1h or 2H rather than 30M"); Bishop's own
   material also allows 30M. This mechanized reading -- the sweep+reclaim
   pattern itself constitutes the V/A shape, rather than a separate V/A
   formation required afterward -- is a judgment call flagged here, not a
   literal transcription; the user separately acknowledged this class of
   pattern is "best on intelligence system" and only approximately
   mechanizable.

3. `classify_entry_pattern()` -- Video 14's 3 execution-facing patterns
   (a restatement of Video 13's exhaustive 4-branch decision tree):
     - DIRECT_MITIGATION: the very next candle taps the new key level
       directly and continues [Video 13 branches 1 and 3].
     - FRESH_IRL_REQUIRED: the next candle approaches but doesn't tap the
       new level -- that candle becomes fresh internal range liquidity
       that must be swept before continuing [branch 2].
     - NESTED_DISRESPECT: instead of respecting the new level, two more
       candles form ANOTHER open-close that then gets disrespected
       [branch 4] -- triggers the ~70% "return to the closer level" rule
       (Phase 2's key-level ranking already captures that preference).

4. IRL -> ERL. "Price always moves from IRL to ERL" is the sequence the
   whole strategy rests on, and FRESH_IRL_REQUIRED is the case where that
   sequence has NOT started yet: price did not come back and tap the
   level, a fresh internal-range-liquidity candle formed in front of it
   instead, and per the source that candle "must be swept before
   continuing". This module only CLASSIFIES that situation (and reports
   the IRL's price); what to do about an entry that hasn't seen the sweep
   yet is runner.py's `irl_mode`.

   An earlier reading had this as "IRL formation is NECESSARY for an
   ORIGIN trade but OPTIONAL for a CONTINUATION trade", exposed as an
   `irl_required(trade_kind)` predicate. That predicate is gone, together
   with the origin/continuation classification it took as input: markets
   are fractal, so an origin exists inside a continuation and a single
   global label for a trade cannot be right (direct user correction). The
   IRL->ERL requirement itself survives that correction unchanged -- it
   just applies to every trade rather than to a labelled subset.

5. Stop-loss placement (Video 13, direct student Q&A, plus a user-supplied
   Bishop-supplementary chart cross-check -- REVISED by a later, more
   extensive user walkthrough: stop-loss is keyed to WHICH CONFIRMATION-
   ENTRY TRIGGER fired, NOT to origin-vs-continuation. The old framing
   below this point in the file's history -- "origin" as its own
   stop-loss category, anchored to the swept liquidity point and taking
   priority for such trades -- was a misreading the user directly
   corrected, and the classification it depended on has since been
   removed outright (see point 4). The 4 TRIGGER-keyed rules, each a
   distinct mechanized formula:
     - plug and play (imbalance overlapping the key level): stop just
       past the FAR edge of that specific imbalance (the side price would
       have to fully clear to invalidate the "came here to sweep
       liquidity and rebalance THIS gap" thesis) plus a small pip buffer
       (`imbalance_stop_loss()`). Visually confirmed against a real
       GBPUSD plug-and-play chart. Takes priority over the other 3 rules
       whenever an overlapping imbalance exists -- this is what "plug and
       play" actually is, regardless of which trigger geometry also fired
       on the same candle.
     - engulfing: a pad beyond whichever is MORE EXTREME between the
       engulfing candle's own wick and the engulfed candle's wick
       (`engulfing_stop_loss()`) -- "the engulfing candle might sweep the
       engulfed candle... the lowest btw both of them," per the user's
       direct correction (an earlier version of this rule used only the
       engulfing candle's own wick).
     - 4th man confirmation: a pad below/above the low/high of the candle
       that did the sweeping (`fourth_man_stop_loss()`) -- the DEFAULT
       only; if that candle's wick is unusually wide, this is overridden
       by the universal fallback below.
     - breakout-as-entry (NOT YET WIRED as its own detected trigger in
       runner.py -- see its module docstring): not just the breakout
       candle's low, but the low of the WHOLE LEG that produced the
       breakout (`breakout_leg_stop_loss()`, not yet added since nothing
       calls it yet).
   UNIVERSAL FALLBACK, applying to ALL FOUR trigger types alike: if the
   trigger's own natural anchor comes out unreasonably wide, fall back to
   placing the stop below/above the H4 key level the setup rejected from
   (the reaction level itself) instead -- "if the logic is correct and
   price shouldn't come back to it... The probability is like 1 or 2 out
   of 10" (direct user quote). `origin_stop_loss()` (kept, name notwith-
   standing -- see its own docstring) supplies this fallback's formula;
   runner.py's `_natural_stop_too_wide()` decides when to use it. Also:
   when multiple same-type key levels sit close together, the stop must
   cover ALL of them still plausibly reachable, not just the nearest --
   NOT YET implemented (flagged, not silently skipped).

6. Entry style (Section 5, "both sanctioned -- build/test both"):
   Aggressive enters directly off the key-level+imbalance setup;
   Conservative waits for the lower-timeframe confirmation candle's close.
"""

from dataclasses import dataclass
from enum import Enum

from .candles import Candle
from .structure import Direction, body_closes_beyond, is_swing_high, is_swing_low
from .key_levels import KeyLevel, detect_open_close_level, is_disrespected


def is_engulfing(prev: Candle, curr: Candle, direction: Direction) -> bool:
    if direction == Direction.BULLISH:
        return (prev.close < prev.open and curr.close > curr.open
                and curr.open <= prev.close and curr.close >= prev.open)
    return (prev.close > prev.open and curr.close < curr.open
            and curr.open >= prev.close and curr.close <= prev.open)


def fourth_man_confirmation_level(prev: Candle, curr: Candle) -> KeyLevel | None:
    """"4th man confirmation" -- see module docstring point 2. `curr`
    sweeps one side of `prev`'s range, closes back INTO it, while `prev`'s
    OTHER side stays untouched:
      - BULLISH: curr.low < prev.low (swept), curr.close > prev.low
        (reclaimed), curr.high < prev.high (prev's high still standing).
      - BEARISH: mirror -- curr.high > prev.high, curr.close < prev.high,
        curr.low > prev.low (prev's low still standing).
    Returns a V-shape (bullish) / A-shape (bearish) KeyLevel at `curr`'s
    close (key_levels.py's closing-price convention), or None if neither
    side's conditions hold."""
    if curr.low < prev.low and curr.close > prev.low and curr.high < prev.high:
        return KeyLevel(curr.time, curr.close, "V", Direction.BULLISH)
    if curr.high > prev.high and curr.close < prev.high and curr.low > prev.low:
        return KeyLevel(curr.time, curr.close, "A", Direction.BEARISH)
    return None


class EntryPattern(Enum):
    DIRECT_MITIGATION = "direct_mitigation"
    FRESH_IRL_REQUIRED = "fresh_irl_required"
    NESTED_DISRESPECT = "nested_disrespect"


@dataclass(frozen=True)
class EntryClassification:
    pattern: EntryPattern
    reference_level: KeyLevel               # the level to actually enter against
    fresh_irl_price: float | None = None    # set only for FRESH_IRL_REQUIRED


def classify_entry_pattern(new_key_level: KeyLevel, following: list[Candle]) -> EntryClassification | None:
    """`following`: the candles immediately after the engulfing candle
    that created `new_key_level`. Returns None if there's nothing to
    classify yet (no candles after the engulf)."""
    if not following:
        return None

    first = following[0]
    if first.low <= new_key_level.price <= first.high:
        return EntryClassification(EntryPattern.DIRECT_MITIGATION, new_key_level)

    if len(following) >= 3:
        nested = detect_open_close_level(following[0], following[1])
        if nested is not None and is_disrespected(following[2], nested):
            return EntryClassification(EntryPattern.NESTED_DISRESPECT, nested)

    fresh_irl_price = first.low if new_key_level.default_bias == Direction.BULLISH else first.high
    return EntryClassification(EntryPattern.FRESH_IRL_REQUIRED, new_key_level, fresh_irl_price)


def origin_stop_loss(structural_extreme: float, direction: Direction,
                      padding_pips: float = 1.0, pip_size: float = 0.0001) -> float:
    """Despite the name (kept for the sake of its existing callers/tests
    predating the trigger-type stop-loss rework -- see module docstring
    point 5), this is now used for TWO distinct roles that happen to
    share the identical "pad beyond a specific reference price" formula:
    (1) historically, an origin trade's stop anchored to the swept
    liquidity point; (2) the UNIVERSAL cross-trigger fallback -- pass the
    H4 key level's own price (the level the setup rejected from) as
    `structural_extreme` when a trigger's natural stop anchor is too wide
    (see runner.py's `_natural_stop_too_wide()`)."""
    pad = padding_pips * pip_size
    return structural_extreme - pad if direction == Direction.BULLISH else structural_extreme + pad


def engulfing_stop_loss(engulfing_extreme: float, engulfed_extreme: float, direction: Direction,
                         padding_pips: float = 1.0, pip_size: float = 0.0001) -> float:
    """A pad beyond whichever of the two candles' wicks is MORE EXTREME --
    "the engulfing candle might sweep the engulfed candle... the lowest
    btw both of them" (direct user correction; an earlier version of this
    rule used only the engulfing candle's own wick). `engulfing_extreme`/
    `engulfed_extreme` are each candle's own low (bullish) or high
    (bearish)."""
    pad = padding_pips * pip_size
    if direction == Direction.BULLISH:
        return min(engulfing_extreme, engulfed_extreme) - pad
    return max(engulfing_extreme, engulfed_extreme) + pad


def fourth_man_stop_loss(sweep_candle_extreme: float, direction: Direction,
                          padding_pips: float = 1.0, pip_size: float = 0.0001) -> float:
    """A pad below/above the low/high of the candle that did the sweeping
    -- the DEFAULT only; the user's own judgment overrides this when that
    candle's wick is unusually wide (see the universal fallback, module
    docstring point 5)."""
    pad = padding_pips * pip_size
    return sweep_candle_extreme - pad if direction == Direction.BULLISH else sweep_candle_extreme + pad


def continuation_stop_loss(entry_price: float, direction: Direction,
                            pips: float = 10.0, pip_size: float = 0.0001) -> float:
    dist = pips * pip_size
    return entry_price - dist if direction == Direction.BULLISH else entry_price + dist


def tight_stop_loss_no_irl(engulfed_candle_extreme: float, direction: Direction,
                            padding_pips: float = 1.0, pip_size: float = 0.0001) -> float:
    """Video 12's optional-IRL continuation variant: tighter than the
    usual 10-11 pip continuation stop -- just past the engulfed candle's
    own extreme plus a small buffer."""
    pad = padding_pips * pip_size
    return engulfed_candle_extreme - pad if direction == Direction.BULLISH else engulfed_candle_extreme + pad


def imbalance_stop_loss(imbalance_low: float, imbalance_high: float, direction: Direction,
                         padding_pips: float = 1.0, pip_size: float = 0.0001) -> float:
    """"Plug and play" continuation stop, scoped to trades whose key level
    overlaps a specific imbalance (FVG): price is expected to sweep
    liquidity and rebalance THAT gap, and has no logical reason to trade
    beyond its far edge to do so. Stop sits just past the far edge (the
    side away from current price -- the side price would have to fully
    clear to invalidate the fill-the-gap thesis) plus a small pip buffer,
    mirroring `origin_stop_loss`'s/`tight_stop_loss_no_irl`'s padding
    convention. `imbalance_low`/`imbalance_high` bound the gap itself
    (an `Imbalance`'s `low`/`high` fields), not the wider displacement
    candle's own range."""
    pad = padding_pips * pip_size
    return imbalance_low - pad if direction == Direction.BULLISH else imbalance_high + pad


class EntryStyle(Enum):
    AGGRESSIVE = "aggressive"
    CONSERVATIVE = "conservative"


def aggressive_entry_price(key_level: KeyLevel) -> float:
    """Enter directly once the key-level+imbalance setup is fully formed, without waiting for confirmation."""
    return key_level.price


def conservative_entry_price(confirmation_candle: Candle) -> float:
    """Wait for the full lower-timeframe confirmation trigger (e.g. an engulfing candle) before entering."""
    return confirmation_candle.close


# How far back to look for the open-close key level a return is buying
# from. Generous, because the level only has to still be standing --
# formation, disrespect and return can be spread over a session.
OPEN_CLOSE_LOOKBACK = 20


def open_close_disrespect_entry(candles: list[Candle], idx: int, direction: Direction,
                                 lookback: int = OPEN_CLOSE_LOOKBACK) -> KeyLevel | None:
    """The confirmation entry this project has been calling "engulfing".

    It is not a candlestick engulfing. Operator, 2026-09-19, confirming
    the reading taken off bishop-entries-part5 at 08:00-09:15:

        "we have 2 candles to the downside forming an open close kl, the
         third candle closes above the open close kl i.e. has
         disrespected that open close kl, then that open close kl can be
         used for a buying entry"
        "Yes we wait for price to come back to the bearish open close,
         to now buy from it."

    Four steps, bullish case, mirrored for bearish:

      1. two consecutive BEARISH candles with overlapping open/close
         ranges form a bearish open-close key level
      2. a later candle CLOSES ABOVE it -- the disrespect. It need not be
         a bullish candle: "it doesn't necessarily mean it can be a
         bullish candle, sometimes the candle can be below"
      3. price comes BACK DOWN to that level
      4. buy from it

    `idx` is the candle being tested as step 4 -- the return. Returns the
    level being bought/sold from, or None.

    What this replaces: `is_engulfing()`, which required prev bearish,
    curr bullish and curr's body covering prev's. That is a different
    pattern that happens to share the name, and it was the engine's
    primary entry trigger. Neither the two-candle open-close formation
    nor the close beyond it appears anywhere in that test.
    """
    curr = candles[idx]
    # Step 4: this candle must actually trade back to the level.
    want_bearish_level = direction == Direction.BULLISH

    start = max(1, idx - lookback)
    best = None
    for i in range(start, idx):
        level = detect_open_close_level(candles[i - 1], candles[i])
        if level is None:
            continue
        # A bullish entry buys from a level that was originally BEARISH
        # (two down candles) and then got disrespected upward.
        if want_bearish_level != (level.default_bias == Direction.BEARISH):
            continue
        # Step 2: some candle after it closed beyond it, before now.
        disrespected_at = None
        for j in range(i + 1, idx):
            if is_disrespected(candles[j], level):
                disrespected_at = j
                break
        if disrespected_at is None:
            continue
        # Step 3: price is back at the level on this candle.
        if not (curr.low <= level.price <= curr.high):
            continue
        # Nearest such level to the return wins -- the one price is
        # actually reacting from, not an older one further away.
        if best is None or i > best[0]:
            best = (i, level)
    return best[1] if best else None


# How far back from the confirmation candle to look for the minor swing
# the reaction created. Same order as OPEN_CLOSE_LOOKBACK -- the taught
# rule never states a number, and section 9 of the spec records that as
# an open question rather than pretending otherwise.
REACTION_STRUCTURE_LOOKBACK = 20


def _recent_minor_swing(candles: list[Candle], idx: int, direction: Direction,
                        lookback: int = REACTION_STRUCTURE_LOOKBACK) -> int | None:
    """Index of the most recent minor swing the reaction left behind: a
    swing HIGH for a bullish entry, a swing LOW for a bearish one.

    n=1 fractal, and only swings decidable BY `idx` are eligible -- a
    1-bar fractal at j is confirmed at j+1, so j may be at most idx-1.
    Using a swing that is not yet confirmed at entry time is the
    look-ahead this project already removed once (see
    timeframes.infer_bar_length and the 2026-09-18 review, finding 1)."""
    start = max(1, idx - lookback)
    for j in range(idx - 1, start - 1, -1):
        if j + 1 > idx:
            continue
        if direction == Direction.BULLISH:
            if is_swing_high(candles, j, n=1):
                return j
        else:
            if is_swing_low(candles, j, n=1):
                return j
    return None


def _reaction_structure(candles: list[Candle], idx: int, direction: Direction,
                        lookback: int = REACTION_STRUCTURE_LOOKBACK):
    """(broke, swept) for the candle at `idx`.

    Both of Bishop's highest-rated confirmations share a skeleton, drawn
    side by side on one screen in bishop-entries-part5 (see SLK_SPEC.md
    5.4 and 5.5). Bullish case:

        price comes into the key level, makes a low, lifts leaving a
        MINOR SWING HIGH, and then closes back above that high.

    `broke` is that close. The frame settles what gets broken: at
    part5 t=420 he marks the reference with an anchored segment at
    1.86789, which sits ABOVE the key level at 1.86700. It is the minor
    swing high the reaction itself created, NOT the key level.

    `swept` is the one extra leg that separates the two. In 5.5 price
    comes back down after the minor high and makes a LOWER low than the
    first one -- measured off the drawing, ~1.86570 against ~1.86660 --
    taking that low's liquidity before breaking up.

    Returned together so the two triggers stay mutually exclusive by
    construction rather than by the order a caller happens to check
    them in."""
    j = _recent_minor_swing(candles, idx, direction, lookback)
    if j is None:
        return False, False

    level = candles[j].high if direction == Direction.BULLISH else candles[j].low
    broke = body_closes_beyond(candles[idx], level, direction)
    if not broke:
        return False, False

    # The low (bullish) that preceded the minor high -- the liquidity a
    # sweep goes after.
    start = max(0, idx - lookback)
    if direction == Direction.BULLISH:
        first = min((c.low for c in candles[start:j]), default=None)
        swept = first is not None and any(
            c.low < first for c in candles[j + 1:idx + 1])
    else:
        first = max((c.high for c in candles[start:j]), default=None)
        swept = first is not None and any(
            c.high > first for c in candles[j + 1:idx + 1])
    return True, swept


def breakout_entry(candles: list[Candle], idx: int, direction: Direction,
                   lookback: int = REACTION_STRUCTURE_LOOKBACK) -> bool:
    """SLK_SPEC.md 5.4. A close beyond the minor swing the reaction left,
    with NO prior sweep of the earlier extreme -- that case is 5.5."""
    broke, swept = _reaction_structure(candles, idx, direction, lookback)
    return broke and not swept


def sweep_break_entry(candles: list[Candle], idx: int, direction: Direction,
                      lookback: int = REACTION_STRUCTURE_LOOKBACK) -> bool:
    """SLK_SPEC.md 5.5. The same break, but price first took out the
    earlier low's (or high's) liquidity.

    Bishop rates this and 5.4 above every other confirmation: "if you
    ask me which ones are likely best, personally I would tell you these
    two ... if you have these two, [missing it] is a missed entry"
    (part5 t=420-435)."""
    broke, swept = _reaction_structure(candles, idx, direction, lookback)
    return broke and swept
