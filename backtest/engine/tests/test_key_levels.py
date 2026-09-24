import pandas as pd
import pytest

from ..candles import Candle
from ..structure import Direction
from ..key_levels import (
    detect_key_levels, detect_open_close_level, is_disrespected,
    count_tests_before_disrespect, is_qmr_level,
)


def C(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def test_detects_a_shape_close_peak():
    # Closes rise into index 2 then fall away -- a close-price peak, sell bias.
    candles = [
        C(0, 1.10, 1.11, 1.09, 1.101),
        C(1, 1.101, 1.12, 1.10, 1.108),
        C(2, 1.108, 1.13, 1.105, 1.115),  # close peak
        C(3, 1.115, 1.116, 1.10, 1.109),
        C(4, 1.109, 1.110, 1.095, 1.100),
    ]
    levels = detect_key_levels(candles, n=2)
    a_shapes = [lvl for lvl in levels if lvl.shape == "A"]
    assert len(a_shapes) == 1
    assert a_shapes[0].price == pytest.approx(1.115)
    assert a_shapes[0].default_bias == Direction.BEARISH


def test_detects_v_shape_close_trough():
    candles = [
        C(0, 1.10, 1.11, 1.09, 1.100),
        C(1, 1.100, 1.101, 1.08, 1.090),
        C(2, 1.090, 1.091, 1.07, 1.080),  # close trough
        C(3, 1.080, 1.095, 1.079, 1.088),
        C(4, 1.088, 1.099, 1.087, 1.095),
    ]
    levels = detect_key_levels(candles, n=2)
    v_shapes = [lvl for lvl in levels if lvl.shape == "V"]
    assert len(v_shapes) == 1
    assert v_shapes[0].price == pytest.approx(1.080)
    assert v_shapes[0].default_bias == Direction.BULLISH


def test_open_close_level_two_down_candles():
    c1 = C(0, 1.1050, 1.1055, 1.1015, 1.1020)  # bearish: close < open
    c2 = C(1, 1.1020, 1.1022, 1.0990, 1.1000)  # bearish, opens where c1 closed
    level = detect_open_close_level(c1, c2)
    assert level is not None
    assert level.shape == "open_close"
    assert level.default_bias == Direction.BEARISH


def test_open_close_level_rejects_non_overlapping():
    c1 = C(0, 1.1050, 1.1055, 1.1015, 1.1020)
    c2 = C(1, 1.0500, 1.0522, 1.0400, 1.0450)  # bearish but no overlap with c1's range
    assert detect_open_close_level(c1, c2) is None


def test_open_close_level_rejects_mixed_direction():
    c1 = C(0, 1.1050, 1.1055, 1.1015, 1.1020)  # bearish
    c2 = C(1, 1.1020, 1.1060, 1.1015, 1.1055)  # bullish
    assert detect_open_close_level(c1, c2) is None


def test_disrespect_flips_a_shape():
    level_candle = C(2, 1.108, 1.13, 1.105, 1.115)
    from ..key_levels import KeyLevel
    a_level = KeyLevel(level_candle.time, 1.115, "A", Direction.BEARISH)

    respecting = C(3, 1.110, 1.116, 1.108, 1.112)   # closes below level -- respects sell bias
    disrespecting = C(4, 1.112, 1.125, 1.111, 1.120)  # closes ABOVE level -- disrespects

    assert not is_disrespected(respecting, a_level)
    assert is_disrespected(disrespecting, a_level)


def test_count_tests_before_disrespect():
    from ..key_levels import KeyLevel
    level = KeyLevel(pd.Timestamp("2024-01-01"), 1.1000, "A", Direction.BEARISH)

    candles_after = [
        # test 1: touches 1.1000, closes back below -- respects
        C(0, 1.098, 1.1005, 1.097, 1.099),
        # test 2: touches again, respects again
        C(1, 1.099, 1.1003, 1.098, 1.0995),
        # disrespect: closes above 1.1000
        C(2, 1.0995, 1.105, 1.099, 1.103),
    ]

    test_count, disrespect_time = count_tests_before_disrespect(candles_after, level)
    assert test_count == 2
    assert disrespect_time == candles_after[2].time
    assert is_qmr_level(test_count) is True


def test_count_tests_never_disrespected_within_window():
    from ..key_levels import KeyLevel
    level = KeyLevel(pd.Timestamp("2024-01-01"), 1.1000, "A", Direction.BEARISH)
    candles_after = [
        C(0, 1.098, 1.1005, 1.097, 1.099),
        C(1, 1.099, 1.1003, 1.098, 1.0995),
    ]
    test_count, disrespect_time = count_tests_before_disrespect(candles_after, level)
    assert test_count == 2
    assert disrespect_time is None


def _zig(pts, base=None):
    import pandas as pd
    from ..candles import Candle
    b = base or pd.Timestamp("2026-01-01", tz="UTC")
    return [Candle(b + pd.Timedelta(hours=i), lo, hi, lo, hi, 1000)
            for i, (lo, hi) in enumerate(pts)]


def test_quasimodo_is_the_pattern_and_the_level_is_the_left_shoulder():
    """L -> H -> LL (below L) -> HH (above H), then buy the ORIGINAL L.

    The operator's own diagram labels that first L the "Left Shoulder
    Level", and it is the tradeable price. Nothing about imbalances is
    involved: "a QMR is a QMR, nothing much about it. It must NOT
    overlap an imbalance. Any kl can overlap an imbalance."
    (2026-09-22)"""
    from ..key_levels import detect_quasimodo_levels
    from ..structure import Direction

    c = _zig([(1.1020, 1.1030), (1.1000, 1.1010), (1.1030, 1.1040),
              (1.1050, 1.1060), (1.1030, 1.1040), (1.0980, 1.0990),
              (1.1030, 1.1040), (1.1070, 1.1080), (1.1040, 1.1050),
              (1.1035, 1.1045)])
    levels = detect_quasimodo_levels(c, n=1)
    assert len(levels) == 1
    lvl = levels[0]
    assert lvl.price == pytest.approx(1.1000), "the level is the LEFT SHOULDER"
    assert lvl.shape == "V" and lvl.default_bias == Direction.BULLISH


def test_no_quasimodo_when_the_third_swing_does_not_exceed_the_first():
    """L -> H -> higher low -> HH is an uptrend, not a Quasimodo. The
    LL must actually take out the left shoulder's low."""
    from ..key_levels import detect_quasimodo_levels

    c = _zig([(1.1020, 1.1030), (1.1000, 1.1010), (1.1030, 1.1040),
              (1.1050, 1.1060), (1.1030, 1.1040), (1.1010, 1.1020),
              (1.1030, 1.1040), (1.1070, 1.1080), (1.1040, 1.1050),
              (1.1035, 1.1045)])
    assert detect_quasimodo_levels(c, n=1) == []


def test_the_level_is_not_knowable_before_the_fourth_swing_confirms():
    """Dating a QM level from its left shoulder would make it appear
    long before anyone could have seen the pattern -- the look-ahead
    removed on 2026-09-18. confirmed_at comes from the FOURTH swing."""
    from ..key_levels import detect_quasimodo_levels, known_at

    c = _zig([(1.1020, 1.1030), (1.1000, 1.1010), (1.1030, 1.1040),
              (1.1050, 1.1060), (1.1030, 1.1040), (1.0980, 1.0990),
              (1.1030, 1.1040), (1.1070, 1.1080), (1.1040, 1.1050),
              (1.1035, 1.1045)])
    lvl = detect_quasimodo_levels(c, n=1)[0]
    # Left shoulder is candle 1; the HH is candle 7 and confirms at 8.
    assert lvl.time == c[1].time
    assert known_at(lvl) > c[7].time


def test_same_kind_swings_collapse_so_the_zigzag_alternates():
    """Without collapsing, a run of three highs reads as high-low-high
    and the pattern matches on noise."""
    from ..key_levels import _alternating_swings

    c = _zig([(1.1000, 1.1010), (1.1020, 1.1030), (1.1010, 1.1020),
              (1.1040, 1.1050), (1.1005, 1.1015), (1.1000, 1.1008)])
    kinds = [k for _, k, _ in _alternating_swings(c, n=1)]
    assert all(a != b for a, b in zip(kinds, kinds[1:])), kinds


def test_a_level_that_only_paused_price_has_not_sponsored_a_move():
    """plug-and-play t=869: "that A-shaped key level MUST HAVE SPONSORED
    some level of sales to the downside".

    The engine traded every level its detector emitted, which is many
    times what anyone draws by hand. This is the qualification that was
    missing: the level has to have already worked."""
    from ..key_levels import sponsored_a_move, KeyLevel
    from ..structure import Direction

    level = KeyLevel(time=0, price=1.1050, shape="A",
                     default_bias=Direction.BEARISH, confirmed_at=0)

    def bar(i, lo, hi):
        return Candle(time=i, open=(lo + hi) / 2, high=hi, low=lo,
                      close=(lo + hi) / 2, volume=0)

    # Price rises from 1.1000 into the level, then falls back THROUGH
    # where the rise began: the level did its job.
    worked = [bar(0, 1.1000, 1.1010), bar(1, 1.1020, 1.1035),
              bar(2, 1.1040, 1.1055),            # touches 1.1050
              bar(3, 1.1015, 1.1045), bar(4, 1.0990, 1.1020)]
    assert sponsored_a_move(worked, level) is True

    # Same approach, but price only stalls -- it never undoes the leg
    # that brought it there.
    paused = [bar(0, 1.1000, 1.1010), bar(1, 1.1020, 1.1035),
              bar(2, 1.1040, 1.1055),
              bar(3, 1.1030, 1.1048), bar(4, 1.1035, 1.1052)]
    assert sponsored_a_move(paused, level) is False

    # Never reached: no record, so no claim.
    untested = [bar(0, 1.1000, 1.1010), bar(1, 1.1005, 1.1015)]
    assert sponsored_a_move(untested, level) is False


def test_sponsored_a_move_mirrors_for_a_bullish_level():
    from ..key_levels import sponsored_a_move, KeyLevel
    from ..structure import Direction

    level = KeyLevel(time=0, price=1.0950, shape="V",
                     default_bias=Direction.BULLISH, confirmed_at=0)

    def bar(i, lo, hi):
        return Candle(time=i, open=(lo + hi) / 2, high=hi, low=lo,
                      close=(lo + hi) / 2, volume=0)

    worked = [bar(0, 1.0990, 1.1000), bar(1, 1.0965, 1.0980),
              bar(2, 1.0945, 1.0960),            # touches 1.0950
              bar(3, 1.0955, 1.0985), bar(4, 1.0980, 1.1010)]
    assert sponsored_a_move(worked, level) is True
