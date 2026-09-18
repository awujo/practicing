"""
Key-level detection -- STRATEGY.md Section 5.

Three shapes, all marked on CLOSING prices (not wicks/highs-lows, per
Section 5's explicit resolution):

1. A-shape: a close-price peak (price rises into it then closes back
   down) -- default bias SELL.
2. V-shape: a close-price trough (mirror) -- default bias BUY.
3. Open-close: two consecutive same-direction candles whose open/close
   ranges overlap -- two down candles = sell continuation, two up = buy
   continuation.

Universal flip rule: ANY key-level type flips its default bias once
price DISRESPECTS it -- a body close beyond the level in the opposite
direction (reuses structure.py's body_closes_beyond, the same CRITICAL
wick-vs-close rule from Section 4). STRATEGY.md qualifies this as an
"impulsive move" beyond the level; there's no precise definition of
"impulsive" given anywhere, so this implementation treats any qualifying
body close as a disrespect -- an impulsiveness filter isn't implemented,
flagged here as a known simplification rather than silently assumed away.

QMR resolution (Video 17, Section 5/9): a level tested/respected 2+ times
before finally being disrespected is the preferred return target
(~80%). `count_tests_before_disrespect` walks forward from a level's
formation and counts how many times price touched it without disrespecting
it, stopping at the disrespect event (or end of data).
"""

from dataclasses import dataclass

from .candles import Candle
from .structure import Direction, body_closes_beyond
from .timeframes import bar_length as _infer_bar_length, closes_at


@dataclass(frozen=True)
class KeyLevel:
    """`confirmed_at`: when this level first becomes knowable in a live,
    candle-by-candle replay. Two separate lags go into it:

      * the FRACTAL lag -- an A/V level is a `is_close_peak`/
        `is_close_trough` test needing n bars either side, so it cannot be
        called until bar `i + n`. Added 2026-08-28, see OPEN_QUESTIONS.md's
        "Backtest replay may have a small (~n-bar) lookahead bias".
      * the BAR-CLOSE lag -- that bar is stamped at its OPEN and has to
        finish before anyone can read it. Added 2026-09-18 (review finding
        1); without it every level, including open_close ones, was
        readable a full bar early.

    None still means "same as `time`", which is the pre-2026-09-18
    reading and the optimistic one. It survives only for levels built
    outside a series (`classify_entry_pattern`'s nested levels)."""
    time: object
    price: float
    shape: str  # "A" | "V" | "open_close"
    default_bias: Direction  # expected reaction direction: BEARISH (sell) or BULLISH (buy)
    confirmed_at: object = None


def known_at(level: KeyLevel) -> object:
    """The time a KeyLevel's existence is actually usable in a
    candle-by-candle replay -- see `KeyLevel`'s own docstring. Any caller
    that filters/bisects levels by time for ELIGIBILITY (not just
    identity/display) must use this, not `.time` directly."""
    return level.confirmed_at if level.confirmed_at is not None else level.time


def _opposite(direction: Direction) -> Direction:
    return Direction.BULLISH if direction == Direction.BEARISH else Direction.BEARISH


def is_close_peak(candles: list[Candle], idx: int, n: int = 2) -> bool:
    if idx < n or idx + n >= len(candles):
        return False
    pivot = candles[idx].close
    return (all(candles[idx - i].close <= pivot for i in range(1, n + 1))
            and all(candles[idx + i].close <= pivot for i in range(1, n + 1)))


def is_close_trough(candles: list[Candle], idx: int, n: int = 2) -> bool:
    if idx < n or idx + n >= len(candles):
        return False
    pivot = candles[idx].close
    return (all(candles[idx - i].close >= pivot for i in range(1, n + 1))
            and all(candles[idx + i].close >= pivot for i in range(1, n + 1)))


def _oc_range(c: Candle) -> tuple[float, float]:
    return (min(c.open, c.close), max(c.open, c.close))


def _is_bearish(c: Candle) -> bool:
    return c.close < c.open


def _is_bullish(c: Candle) -> bool:
    return c.close > c.open


def detect_open_close_level(c1: Candle, c2: Candle, bar_length=None) -> KeyLevel | None:
    """Two consecutive same-direction candles with overlapping open/close
    ranges. Returns None if the candles aren't same-direction or don't overlap.

    `bar_length` makes the level knowable at c2's CLOSE rather than its
    open. Optional because `classify_entry_pattern()` builds nested levels
    from two loose candles with no series to measure; omitting it keeps
    the pre-2026-09-18 reading, which is the optimistic one."""
    if _is_bearish(c1) and _is_bearish(c2):
        bias = Direction.BEARISH
    elif _is_bullish(c1) and _is_bullish(c2):
        bias = Direction.BULLISH
    else:
        return None

    lo1, hi1 = _oc_range(c1)
    lo2, hi2 = _oc_range(c2)
    overlap_lo, overlap_hi = max(lo1, lo2), min(hi1, hi2)
    if overlap_lo > overlap_hi:
        return None

    return KeyLevel(c2.time, (overlap_lo + overlap_hi) / 2, "open_close", bias,
                    confirmed_at=closes_at(c2.time, bar_length))


def detect_key_levels(candles: list[Candle], n: int = 2) -> list[KeyLevel]:
    """Scan a candle series for all three key-level shapes. A/V shapes get
    `confirmed_at` set to `n` bars after their own pivot (`candles[i + n]`,
    always in range since is_close_peak/is_close_trough already required
    `idx + n < len(candles)` to return True here) -- see KeyLevel's
    docstring for why."""
    # An A/V pivot needs n bars either side AND the last of those bars
    # has to finish -- `candles[i + n].time` is that bar's OPEN, so using
    # it alone made the level knowable a full bar early (2026-09-18
    # review, finding 1).
    length = _infer_bar_length(candles)
    levels = []
    for i in range(len(candles)):
        if is_close_peak(candles, i, n):
            levels.append(KeyLevel(candles[i].time, candles[i].close, "A", Direction.BEARISH,
                                    confirmed_at=closes_at(candles[i + n].time, length)))
        if is_close_trough(candles, i, n):
            levels.append(KeyLevel(candles[i].time, candles[i].close, "V", Direction.BULLISH,
                                    confirmed_at=closes_at(candles[i + n].time, length)))
    for i in range(len(candles) - 1):
        oc = detect_open_close_level(candles[i], candles[i + 1], bar_length=length)
        if oc is not None:
            levels.append(oc)
    return sorted(levels, key=lambda lvl: lvl.time)


def is_disrespected(candle: Candle, level: KeyLevel) -> bool:
    """A body close beyond the level in the OPPOSITE direction from its default bias."""
    return body_closes_beyond(candle, level.price, _opposite(level.default_bias))


def count_tests_before_disrespect(candles_after: list[Candle], level: KeyLevel) -> tuple[int, object | None]:
    """
    Walk forward from a key level's formation and count how many times
    price touches it (wick trades through) without disrespecting it,
    stopping at the first disrespect (or returning at end of data if
    never disrespected within the given window).

    Returns (test_count, disrespect_time_or_None).
    """
    tests = 0
    for c in candles_after:
        touched = c.low <= level.price <= c.high
        if not touched:
            continue
        if is_disrespected(c, level):
            return tests, c.time
        tests += 1
    return tests, None


def is_qmr_level(test_count: int) -> bool:
    """Section 5/9's resolved QMR threshold: 2+ prior tests before disrespect."""
    return test_count >= 2
