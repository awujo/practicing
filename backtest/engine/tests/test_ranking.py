import pandas as pd
import pytest

from ..structure import Direction
from ..key_levels import KeyLevel
from ..imbalance import Imbalance
from ..ranking import score_candidates, default_to_extreme, DEFAULT_WEIGHTS


def T(hours):
    return pd.Timestamp("2024-01-01") + pd.Timedelta(hours=hours)


def test_level_with_overlap_and_more_tests_outranks_plain_level():
    strong = KeyLevel(T(0), 1.1000, "A", Direction.BEARISH)   # overlaps an imbalance, tested 3x
    weak = KeyLevel(T(10), 1.2000, "A", Direction.BEARISH)    # no overlap, tested 0x, but more recent

    imbalances = [Imbalance(T(0), 1.0990, 1.1010, Direction.BULLISH)]

    ranked = score_candidates([(strong, 3), (weak, 0)], imbalances, weights=DEFAULT_WEIGHTS)

    assert ranked[0].level is strong
    assert ranked[0].imbalance_overlap is True
    assert ranked[0].test_count == 3


def test_recency_only_weighting_prefers_more_recent_level():
    older = KeyLevel(T(0), 1.1000, "A", Direction.BEARISH)
    newer = KeyLevel(T(10), 1.2000, "A", Direction.BEARISH)

    weights = {"imbalance_overlap": 0, "recency": 1.0, "test_count": 0, "imbalance_fill_size": 0}
    ranked = score_candidates([(older, 0), (newer, 0)], [], weights=weights)

    assert ranked[0].level is newer


def test_imbalance_fill_size_can_favor_more_distant_level():
    near = KeyLevel(T(0), 1.1000, "A", Direction.BEARISH)     # small imbalance
    far = KeyLevel(T(0), 1.1500, "A", Direction.BEARISH)      # much larger imbalance

    imbalances = [
        Imbalance(T(0), 1.0995, 1.1005, Direction.BULLISH),   # size 0.0010, overlaps `near`
        Imbalance(T(0), 1.1400, 1.1600, Direction.BULLISH),   # size 0.0200, overlaps `far`
    ]

    weights = {"imbalance_overlap": 0, "recency": 0, "test_count": 0, "imbalance_fill_size": 1.0}
    ranked = score_candidates([(near, 0), (far, 0)], imbalances, weights=weights)

    assert ranked[0].level is far
    assert ranked[0].imbalance_fill_size > ranked[1].imbalance_fill_size


def test_default_to_extreme_picks_farthest_from_current_price():
    close_level = KeyLevel(T(0), 1.1010, "A", Direction.BEARISH)
    far_level = KeyLevel(T(0), 1.2000, "A", Direction.BEARISH)
    current_price = 1.1000

    chosen = default_to_extreme([close_level, far_level], current_price)
    assert chosen is far_level
