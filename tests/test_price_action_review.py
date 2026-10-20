"""Independent review checks for primitives; no historical-trade claims."""
import pandas as pd
import pytest

from bishop.candles import completed
from bishop.price_action import KeyLevel, classify, levels, validated_bars


def test_completed_clock_is_used_instead_of_observed_bar_start():
    start = pd.date_range("2026-10-20T21:00:00Z", periods=3, freq="h")
    h1 = pd.DataFrame({"open": [1., 2., 1.], "high": [3., 3., 3.],
                       "low": [.5, .5, .5], "close": [2., 1., 2.]}, index=start)
    now = pd.Timestamp("2026-10-20T23:00:00Z")
    closed = completed(h1, "H1", now)
    assert len(closed) == 2
    found = levels(closed, as_of=now)
    assert len(found) == 1 and found[0].kind == "A"
    assert found[0].available_at == now
    assert found[0].formed_at == pd.Timestamp("2026-10-20T22:00:00Z")
    assert classify(found[0], closed.iloc[-1], as_of=now) is None


def test_gapped_beyond_observation_is_not_claimed_to_be_structural_bos():
    level = KeyLevel("V", 1., "BUY", "2026-01-01T00:00Z", "2026-01-01T01:00Z")
    # Entire candle is below support. Current primitive reports relative
    # BREAK; stateful crossing and structural BOS remain separate layers.
    candle = pd.Series({"open": .8, "high": .9, "low": .6, "close": .7,
                        "end": pd.Timestamp("2026-01-01T02:00Z")})
    result = classify(level, candle, as_of="2026-01-01T02:00Z")
    assert result.kind == "BREAK" and result.side == "SELL"


def test_explicit_end_column_cannot_be_bypassed_with_an_earlier_index():
    frame = pd.DataFrame({"open": [1.], "high": [2.], "low": [.5], "close": [1.5],
                          "end": [pd.Timestamp("2026-01-01T04:00Z")]},
                         index=pd.DatetimeIndex(["2026-01-01T00:00Z"]))
    with pytest.raises(ValueError, match="future/forming"):
        validated_bars(frame, as_of="2026-01-01T01:00Z")


def test_role_relative_sweep_mirror_and_no_input_mutation():
    level = KeyLevel("A", 2., "SELL", "2026-01-01T00:00Z", "2026-01-01T01:00Z")
    candle = pd.Series({"open": 1.9, "high": 2.1, "low": 1.8, "close": 1.95,
                        "end": pd.Timestamp("2026-01-01T02:00Z")})
    before = candle.copy(deep=True)
    event = classify(level, candle, as_of="2026-01-01T02:00Z")
    assert event.kind == "SWEEP" and event.side == "SELL"
    pd.testing.assert_series_equal(candle, before)
    assert level.side == "SELL"  # Classification never mutates current role.


def test_invalid_ohlc_close_above_high_rejected_before_classification():
    level = KeyLevel("V", 1., "BUY", "2026-01-01T00:00Z", "2026-01-01T01:00Z")
    bad = pd.Series({"open": 1., "high": 1.2, "low": .9, "close": 1.3,
                     "end": pd.Timestamp("2026-01-01T02:00Z")})
    with pytest.raises(ValueError, match="bounds"):
        classify(level, bad, as_of="2026-01-01T02:00Z")
