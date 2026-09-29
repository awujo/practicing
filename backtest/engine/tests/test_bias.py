import pandas as pd
import pytest

from ..candles import Candle
from ..structure import Direction
from ..key_levels import KeyLevel
from ..bias import (
    detect_confirmations, ConfirmationKind, BiasCascade, resolve_effective_bias,
    Confirmation,
)


def C(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def T(hours):
    return pd.Timestamp("2024-01-01") + pd.Timedelta(hours=hours)


def test_plain_breakout_detected_without_prior_sweep():
    # A clean, direct push through a swing high with no prior wick-sweep-and-reverse.
    candles = [
        C(0, 1.100, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.112, 1.104, 1.107),  # swing high, high=1.112
        C(3, 1.107, 1.109, 1.102, 1.104),
        C(4, 1.104, 1.106, 1.100, 1.103),
        C(5, 1.103, 1.108, 1.101, 1.105),
        C(6, 1.105, 1.115, 1.104, 1.113),  # closes straight through 1.112 -- plain breakout
    ]
    confirmations = detect_confirmations(candles, n=2)
    breakouts = [c for c in confirmations if c.kind == ConfirmationKind.BREAKOUT]
    sweep_breaks = [c for c in confirmations if c.kind == ConfirmationKind.SWEEP_BREAK]

    assert any(c.direction == Direction.BULLISH for c in breakouts)
    assert sweep_breaks == []  # no sweep ever happened, so nothing should be tagged sweep_break


def test_plain_breakout_uses_the_swing_candles_close_not_its_wick():
    # Direct user correction: SLK reads breakouts off the LINE CHART (closing
    # prices) throughout, matching how A/V-shape key levels already work --
    # not the swing candle's wick. A later candle that closes beyond the
    # swing candle's CLOSE (1.107) but not beyond its wick HIGH (1.112) must
    # still count as a breakout.
    candles = [
        C(0, 1.100, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.112, 1.104, 1.107),  # swing high: wick high=1.112, close=1.107
        C(3, 1.107, 1.109, 1.102, 1.104),
        C(4, 1.104, 1.106, 1.100, 1.103),
        C(5, 1.103, 1.108, 1.101, 1.105),
        C(6, 1.105, 1.111, 1.104, 1.109),  # closes at 1.109: beyond the swing's CLOSE, not its wick
    ]
    confirmations = detect_confirmations(candles, n=2)
    breakouts = [c for c in confirmations if c.kind == ConfirmationKind.BREAKOUT]
    assert any(c.direction == Direction.BULLISH and c.time == T(6) for c in breakouts)


def test_sweep_break_not_double_counted_as_breakout():
    # Reuses Phase 1's exact sweep+break sequence -- must be tagged SWEEP_BREAK only, not also BREAKOUT.
    candles = [
        C(0, 1.100, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.112, 1.104, 1.107),  # swing high: 1.112
        C(3, 1.107, 1.109, 1.102, 1.104),
        C(4, 1.104, 1.106, 1.095, 1.096),  # swing low: 1.095
        C(5, 1.096, 1.099, 1.097, 1.098),
        C(6, 1.098, 1.101, 1.097, 1.099),
        C(7, 1.099, 1.100, 1.090, 1.097),  # sweep below 1.095
        C(8, 1.097, 1.120, 1.096, 1.115),  # closes back above 1.112 -- sweep+break bullish
    ]
    confirmations = detect_confirmations(candles, n=2)
    at_break_candle = [c for c in confirmations if c.time == T(8)]

    assert len(at_break_candle) == 1
    assert at_break_candle[0].kind == ConfirmationKind.SWEEP_BREAK


def test_close_based_sweep_break_confirms_where_wick_based_does_not_yet():
    """Same line-chart-vs-wick question as the plain breakout, applied to
    the sweep+break half instead -- passed through from detect_confirmations()
    into StructureTracker's own close_based_break."""
    candles = [
        C(0, 1.100, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.112, 1.104, 1.107),  # swing high: wick 1.112, close 1.107
        C(3, 1.107, 1.109, 1.102, 1.104),
        C(4, 1.104, 1.106, 1.095, 1.096),  # swing low: 1.095
        C(5, 1.096, 1.099, 1.097, 1.098),
        C(6, 1.098, 1.101, 1.097, 1.099),
        C(7, 1.099, 1.100, 1.090, 1.097),  # sweeps below 1.095
        C(8, 1.097, 1.110, 1.096, 1.109),  # closes 1.109: past the swing's close, not its wick
    ]
    default_confirmations = detect_confirmations(candles, n=2)
    assert not any(c.kind == ConfirmationKind.SWEEP_BREAK and c.direction == Direction.BULLISH
                    for c in default_confirmations)

    close_based = detect_confirmations(candles, n=2, close_based_sweep_break=True)
    assert any(c.kind == ConfirmationKind.SWEEP_BREAK and c.direction == Direction.BULLISH
               for c in close_based)


def test_bias_flips_when_rejection_and_no_lower_tf_continuation():
    cascade = BiasCascade("Daily")
    cascade.set_initial_bias(Direction.BEARISH, T(0))

    next_key_level = KeyLevel(T(1), 1.1000, "A", Direction.BEARISH)
    rejection_candle = C(2, 1.099, 1.105, 1.098, 1.103)  # closes ABOVE 1.1000 -- rejects+closes new direction

    # Lower timeframe shows nothing continuing the OLD (bearish) direction.
    lower_tf_confirmations = []

    flipped = cascade.check_flip(next_key_level, rejection_candle, lower_tf_confirmations)

    assert flipped is True
    assert cascade.direction == Direction.BULLISH


def test_bias_does_not_flip_when_lower_tf_still_confirms_original_direction():
    cascade = BiasCascade("Daily")
    cascade.set_initial_bias(Direction.BEARISH, T(0))

    next_key_level = KeyLevel(T(1), 1.1000, "A", Direction.BEARISH)
    rejection_candle = C(2, 1.099, 1.105, 1.098, 1.103)  # rejects+closes new direction

    from ..bias import Confirmation
    # Lower timeframe STILL shows a bearish (original-direction) confirmation.
    lower_tf_confirmations = [Confirmation(T(3), Direction.BEARISH, ConfirmationKind.BREAKOUT, 1.090)]

    flipped = cascade.check_flip(next_key_level, rejection_candle, lower_tf_confirmations)

    assert flipped is False
    assert cascade.direction == Direction.BEARISH  # unchanged -- Video 16's resolved ambiguity


def test_bias_does_not_flip_without_rejection():
    cascade = BiasCascade("Daily")
    cascade.set_initial_bias(Direction.BEARISH, T(0))

    next_key_level = KeyLevel(T(1), 1.1000, "A", Direction.BEARISH)
    no_rejection_candle = C(2, 1.098, 1.099, 1.095, 1.097)  # still closes below 1.1000 -- respects, no rejection

    flipped = cascade.check_flip(next_key_level, no_rejection_candle, [])

    assert flipped is False
    assert cascade.direction == Direction.BEARISH


def test_weekly_beats_daily_in_priority_hierarchy():
    biases = {"Monthly": None, "Weekly": Direction.BEARISH, "Daily": Direction.BULLISH, "H4": Direction.BULLISH}
    direction, source_tf = resolve_effective_bias(biases)
    assert direction == Direction.BEARISH
    assert source_tf == "Weekly"


def test_falls_through_to_lower_timeframe_when_higher_ones_have_no_bias():
    biases = {"Monthly": None, "Weekly": None, "Daily": None, "H4": Direction.BULLISH}
    direction, source_tf = resolve_effective_bias(biases)
    assert direction == Direction.BULLISH
    assert source_tf == "H4"


def test_an_empty_confirmation_window_is_not_a_confirmation():
    """The bias must not flip on no evidence at all.

    Condition (c) is written as a negative -- "the next lower timeframe
    must ALSO fail to give any further continuation confirmation in the
    original direction" (video-16) -- and an empty window satisfies that
    literally. But BIAS_CONFIRMATION_WINDOW's own comment describes the
    intent positively: "you look at the lower timeframe's MOST RECENT
    breakout, and if it points the new way, the bias has flipped." No
    breakout does not point the new way.

    The 2026-09-22 audit filed this as real but harmless, since the
    window is empty only when the rejection falls after the last
    confirmation -- the tail of the series. That reasoning was
    incomplete: the tail is where LIVE always runs."""
    level = KeyLevel(time=pd.Timestamp("2024-01-10"), price=1.1000, shape="A",
                     default_bias=Direction.BULLISH, confirmed_at=pd.Timestamp("2024-01-10"))
    # A candle that closes through the level -- condition (b) satisfied.
    rejection = Candle(pd.Timestamp("2024-01-11"), 1.1010, 1.1012, 1.0980, 1.0985, 1000)

    # Default: flips on an empty window, which is the behaviour every
    # recorded backtest was produced under.
    loose = BiasCascade("Daily")
    loose.set_initial_bias(Direction.BULLISH, pd.Timestamp("2024-01-01"))
    assert loose.check_flip(level, rejection, []) is True
    assert loose.direction == Direction.BEARISH

    # With the guard: no evidence, no flip.
    strict = BiasCascade("Daily")
    strict.set_initial_bias(Direction.BULLISH, pd.Timestamp("2024-01-01"))
    assert strict.check_flip(level, rejection, [], require_confirmation=True) is False
    assert strict.direction == Direction.BULLISH

    # And the guard must not block a REAL flip: a confirmation exists and
    # points the new way.
    new_way = Confirmation(time=pd.Timestamp("2024-01-11 06:00"),
                           direction=Direction.BEARISH,
                           kind=ConfirmationKind.BREAKOUT, price=1.0980)
    ok = BiasCascade("Daily")
    ok.set_initial_bias(Direction.BULLISH, pd.Timestamp("2024-01-01"))
    assert ok.check_flip(level, rejection, [new_way], require_confirmation=True) is True
    assert ok.direction == Direction.BEARISH


def test_require_touch_blocks_a_candle_that_never_traded_into_the_level():
    """Condition (a), enforced INSIDE check_flip() when require_touch=True.

    Video 16 states the flip test as TWO events: "price trades into the
    next key level ... AND rejects from it". The historical default leaves
    condition (a) to the caller -- replay_bias() filters with
    `c.low <= level.price <= c.high` -- but a hand-built call could pass a
    candle that merely closes through the level without ever wicking into
    it, silently skipping the first event. With the guard on, such a
    candle returns False before the lower timeframe is consulted at all.
    """
    level = KeyLevel(time=pd.Timestamp("2024-01-10"), price=1.1000, shape="A",
                     default_bias=Direction.BULLISH, confirmed_at=pd.Timestamp("2024-01-10"))
    # Closes BELOW the level (condition (b) satisfied) but its whole range
    # sits under the level's price -- it never traded INTO it.
    no_touch = Candle(pd.Timestamp("2024-01-11"), 1.0990, 1.0995, 1.0980, 1.0985, 1000)
    new_way = Confirmation(time=pd.Timestamp("2024-01-11 06:00"),
                           direction=Direction.BEARISH,
                           kind=ConfirmationKind.BREAKOUT, price=1.0980)

    # Guard OFF (default): caller skipped condition (a), flip proceeds --
    # every recorded backtest ran under this contract.
    loose = BiasCascade("Daily")
    loose.set_initial_bias(Direction.BULLISH, pd.Timestamp("2024-01-01"))
    assert loose.check_flip(level, no_touch, [new_way]) is True
    assert loose.direction == Direction.BEARISH

    # Guard ON: no touch, no flip -- and no bias change.
    strict = BiasCascade("Daily")
    strict.set_initial_bias(Direction.BULLISH, pd.Timestamp("2024-01-01"))
    assert strict.check_flip(level, no_touch, [new_way], require_touch=True) is False
    assert strict.direction == Direction.BULLISH


def test_require_touch_still_allows_a_genuine_touch_and_reject():
    """The guard must not block a REAL flip: a candle whose range spans the
    level and closes through it still flips with require_touch=True."""
    level = KeyLevel(time=pd.Timestamp("2024-01-10"), price=1.1000, shape="A",
                     default_bias=Direction.BULLISH, confirmed_at=pd.Timestamp("2024-01-10"))
    # High 1.1012 > level > low 1.0980: traded into the level, closed below.
    rejection = Candle(pd.Timestamp("2024-01-11"), 1.1010, 1.1012, 1.0980, 1.0985, 1000)
    new_way = Confirmation(time=pd.Timestamp("2024-01-11 06:00"),
                           direction=Direction.BEARISH,
                           kind=ConfirmationKind.BREAKOUT, price=1.0980)
    cascade = BiasCascade("Daily")
    cascade.set_initial_bias(Direction.BULLISH, pd.Timestamp("2024-01-01"))
    assert cascade.check_flip(level, rejection, [new_way], require_touch=True) is True
    assert cascade.direction == Direction.BEARISH


def test_require_touch_and_require_confirmation_compose_independently():
    """The two guards cover different conditions ((a) and (c)) and must be
    individually satisfiable when both are on: failing either one blocks
    the flip; passing both allows it."""
    level = KeyLevel(time=pd.Timestamp("2024-01-10"), price=1.1000, shape="A",
                     default_bias=Direction.BULLISH, confirmed_at=pd.Timestamp("2024-01-10"))
    rejection = Candle(pd.Timestamp("2024-01-11"), 1.1010, 1.1012, 1.0980, 1.0985, 1000)
    new_way = Confirmation(time=pd.Timestamp("2024-01-11 06:00"),
                           direction=Direction.BEARISH,
                           kind=ConfirmationKind.BREAKOUT, price=1.0980)
    no_touch = Candle(pd.Timestamp("2024-01-11"), 1.0990, 1.0995, 1.0980, 1.0985, 1000)

    # Both on, touch fails even though confirmation passes -> no flip.
    c1 = BiasCascade("Daily")
    c1.set_initial_bias(Direction.BULLISH, pd.Timestamp("2024-01-01"))
    assert c1.check_flip(level, no_touch, [new_way],
                         require_confirmation=True, require_touch=True) is False
    assert c1.direction == Direction.BULLISH

    # Both on, confirmation empty even though touch passes -> no flip.
    c2 = BiasCascade("Daily")
    c2.set_initial_bias(Direction.BULLISH, pd.Timestamp("2024-01-01"))
    assert c2.check_flip(level, rejection, [],
                         require_confirmation=True, require_touch=True) is False
    assert c2.direction == Direction.BULLISH

    # Both on, both conditions genuinely met -> flip proceeds.
    c3 = BiasCascade("Daily")
    c3.set_initial_bias(Direction.BULLISH, pd.Timestamp("2024-01-01"))
    assert c3.check_flip(level, rejection, [new_way],
                         require_confirmation=True, require_touch=True) is True
    assert c3.direction == Direction.BEARISH

