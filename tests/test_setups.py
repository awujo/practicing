"""Synthetic entry-sequence contracts, not historical teaching replay results."""
from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from bishop.setups import Context, RiskProfile, detect_setups


def bars(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], dtype=float,
                        index=pd.date_range("2026-01-02T10:00Z", periods=len(rows), freq="h"))


def context(**over):
    return Context(**{"side": "BUY", "available_at": "2026-01-02T09:00Z", "origin_tf": "D",
                      "target": 120, "target_available_at": "2026-01-01T00:00Z",
                      "target_kind": "ERL", "target_tf": "H4", **over})


def risk(**over):
    return RiskProfile(**{"mode": "structural_wick", "pip_size": 1, "buffer_pips": .5, **over})


def engulf():
    return bars([[102, 103, 99, 100], [100, 105, 99.5, 104]])


def run(frame, ctx=None, profile=None, **over):
    return detect_setups(frame, context() if ctx is None else ctx, tf="H1",
                         profile=risk() if profile is None else profile,
                         as_of="2026-02-01T00:00Z", **over)


def test_engulf_retest_is_pending_formation_at_second_close():
    frame = engulf()
    result, = run(frame)
    assert result.model == "engulf_retest" and result.side == "BUY"
    assert (result.entry, result.stop, result.target) == (100, 98.5, 120)
    assert result.reference_at == frame.index[0]
    assert result.formed_at == result.available_at == frame.index[1]
    assert result.context_available_at < result.available_at
    assert result.target_kind == "ERL" and result.target_tf == "H4"
    assert not hasattr(result, "fill_time") and not hasattr(result, "status")
    with pytest.raises(FrozenInstanceError):
        result.entry = 999


def test_sell_is_true_mirror_and_stop_protects_higher_wick():
    frame = bars([[98, 101, 97, 100], [100, 100.5, 95, 96]])
    result, = run(frame, context(side="SELL", target=80))
    assert (result.entry, result.stop, result.target) == (100, 101.5, 80)
    assert result.side == "SELL"


def test_oc_break_need_not_engulf_both_candles_and_uses_oc_junction():
    frame = bars([[105, 106, 102, 103], [103, 104, 100, 101], [101, 105, 99, 104]])
    result, = run(frame, models=("oc_break_retest",))
    assert result.model == "oc_break_retest"
    assert result.entry == 103 and result.stop == 98.5
    assert result.available_at == frame.index[2]
    # Break close 104 is below first open 105: engulfing both bodies is not required.
    assert frame["close"].iloc[-1] < frame["open"].iloc[0]


def test_oc_stop_includes_intermediate_wick_not_later_future_extreme():
    frame = bars([[105, 106, 102, 103], [103, 104, 100, 101],
                  [101, 102, 95, 100], [100, 105, 99, 104], [104, 105, 90, 102]])
    found = run(frame, models=("oc_break_retest",))
    oc = next(s for s in found if s.entry == 103)
    assert oc.stop == 94.5 and oc.available_at == frame.index[3]


def test_fixed_owner_profile_changes_only_stop_and_preserves_target_provenance():
    ctx = context(target_kind="ORIGIN_KL", target_tf="D")
    structural, = run(engulf(), ctx)
    fixed, = run(engulf(), ctx, risk(mode="fixed_pips", fixed_stop_pips=3))
    assert structural.stop == 98.5 and fixed.stop == 97
    assert structural.profile == "structural_wick" and fixed.profile == "fixed_pips"
    assert structural.entry == fixed.entry and structural.target == fixed.target == 120
    assert fixed.target_kind == "ORIGIN_KL" and fixed.target_tf == "D"


def test_decimal_pip_padding_has_stable_price_representation():
    frame = bars([[1.1002, 1.1003, 1.0998, 1.1], [1.1, 1.1005, 1.0999, 1.1004]])
    result, = run(frame, context(target=1.12), risk(pip_size=.0001))
    assert result.entry == 1.1 and result.stop == 1.09975


def test_future_context_cannot_retroactively_admit_engulf_or_old_oc_break():
    assert run(engulf(), context(available_at="2026-01-02T12:00Z")) == []
    frame = bars([[105, 106, 102, 103], [103, 104, 100, 101],
                  [101, 105, 99, 104], [104, 106, 103, 105]])
    assert run(frame, context(available_at="2026-01-02T13:00Z"), models=("oc_break_retest",)) == []


def test_target_is_not_silently_selected_from_later_information():
    with pytest.raises(ValueError, match="known"):
        context(target_available_at="2026-01-02T10:00Z")


def test_spent_target_prevents_new_order_toward_already_taken_liquidity():
    frame = bars([[102, 121, 99, 100], [100, 105, 99.5, 104]])
    assert run(frame) == []
    frame = engulf()
    frame.iloc[1, frame.columns.get_loc("high")] = 120
    assert run(frame) == []


def test_body_definition_exact_junction_and_close_beyond_are_explicit():
    frame = engulf()
    frame.iloc[1, frame.columns.get_loc("open")] = 100.1
    assert run(frame) == []  # Exact-junction policy does not invent gap tolerance.
    frame = engulf()
    frame.iloc[1, frame.columns.get_loc("close")] = 102
    assert run(frame) == []  # Equal prior body open is not strict engulf close.


def test_prefix_outputs_are_invariant_to_future_candles_and_target_hit():
    closes = [105, 103, 101, 104, 102, 106, 104, 107, 125]
    opened = [106, *closes[:-1]]
    frame = bars([[o, max(o, c) + 1, min(o, c) - 1, c] for o, c in zip(opened, closes)])
    full = run(frame)
    for n in range(1, len(frame) + 1):
        expected = [s for s in full if s.available_at <= frame.index[n - 1]]
        assert run(frame.iloc[:n]) == expected


def test_forming_candle_and_invalid_prices_fail_closed():
    with pytest.raises(ValueError, match="future/forming"):
        detect_setups(engulf(), context(), tf="H1", profile=risk(), as_of="2026-01-02T10:00Z")
    frame = engulf()
    frame.iloc[1, frame.columns.get_loc("low")] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        run(frame)


@pytest.mark.parametrize("override", [{"pip_size": 0}, {"buffer_pips": -1}, {"fixed_stop_pips": 0},
                                      {"mode": "source_magic"}, {"pip_size": float("nan")}, {"pip_size": True}])
def test_invalid_risk_profiles_are_rejected(override):
    with pytest.raises(ValueError):
        risk(**override)


def test_supported_paths_are_explicit_and_unknown_model_rejected():
    with pytest.raises(ValueError, match="supported"):
        run(engulf(), models=("aggressive_direct",))


def test_context_expiry_is_observed_and_excludes_equal_time_setup():
    frame = engulf()
    assert run(frame, context(expires_at=frame.index[-1])) == []
    assert len(run(frame, context(expires_at=frame.index[-1] + pd.Timedelta(seconds=1)))) == 1
    with pytest.raises(ValueError, match="expiry"):
        context(expires_at="2026-01-02T08:00Z")


def test_close_reference_mode_is_explicit_and_never_tunes_gap_tolerance():
    frame = engulf()
    frame.iloc[1, frame.columns.get_loc("open")] = 100.1
    assert run(frame) == []
    result, = run(frame, level_mode="close_reference")
    assert result.entry == 100  # Reference is source candle close, never gap midpoint.
    with pytest.raises(ValueError, match="level_mode"):
        run(frame, level_mode="nearest_five_pips")
