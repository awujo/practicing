"""Independent causal-engine review; synthetic contracts, not teacher replay."""
import pandas as pd
import pytest

from bishop import bias, structure
from bishop.price_action import levels
from bishop.setups import Context, RiskProfile, detect_setups
from bishop.execution import Costs, Order, simulate


def order(**changes):
    return Order(**{"id": "synthetic-order", "pair": "EURUSD", "side": "BUY", "tf": "H1",
                    "mode": "structural_wick", "entry": 1.1000, "stop": 1.0990, "target": 1.1020,
                    "available_at": "2026-01-05T10:00Z", "expires_at": "2026-01-05T15:00Z",
                    "bias_side": "BUY", "bias_tf": "D", **changes})


def hourly(rows, start="2026-01-05T10:00Z"):
    # Execution input uses hourly STARTS, unlike closed structural input.
    return closed(rows, start=start)


def closed(rows, start="2026-01-01T00:00Z", freq="h"):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=pd.date_range(start, periods=len(rows), freq=freq), dtype=float)


def test_local_structure_events_are_prefix_invariant_and_observable():
    closes = [2., 3., 2.5, 3.5, 2.8, 3.8, 2.4, 3.9, 2.1]
    opens = [closes[0], *closes[:-1]]
    rows = [(o, max(o, c) + .2, min(o, c) - .2, c) for o, c in zip(opens, closes)]
    data = closed(rows)
    full = structure.events(data, as_of=data.index[-1])
    turns = structure.turning_points(data, as_of=data.index[-1])
    assert full and turns
    for point in turns:
        assert point.formed_at < point.available_at
    for event in full:
        assert event.reference_available_at < event.available_at
        assert event.occurred_at == event.available_at
        if event.kind == "SWEEP_BOS":
            assert event.sweep_at < event.available_at
    for n in range(1, len(data) + 1):
        now = data.index[n - 1]
        assert structure.events(data.iloc[:n], as_of=now) == [e for e in full if e.available_at <= now]
        assert structure.turning_points(data.iloc[:n], as_of=now) == [p for p in turns if p.available_at <= now]


def prebroken_reference_case():
    origin = closed([(4.2, 4.3, 4., 4.1), (4.1, 4.2, 3.5, 3.6),
                     (3.6, 4.1, 3.5, 4.), (4., 4.2, 3.4, 3.8)], freq="4h")
    origin["start"] = origin.index - pd.Timedelta(hours=4)
    lower = closed([(1., 1.1, .9, 1.), (1., 3.1, .9, 3.),
                    (3., 3.1, 1.9, 2.), (2., 4.1, 1.9, 4.),
                    (4., 4.1, 3.4, 3.8), (3.8, 4., 3.7, 3.9),
                    (3.9, 4.1, 3.8, 4.), (4., 4.1, 3.7, 3.8)],
                   start="2026-01-01T05:00Z")
    return origin, lower


def test_a_reference_already_broken_before_touch_is_not_a_fresh_confirmation():
    origin, lower = prebroken_reference_case()
    found = bias.find_stories(origin, lower, origin_tf="H4", confirmation_tf="H1",
                              as_of=origin.index[-1])
    # The known H=3 broke at08:00, before09:00 KL touch. Every later close
    # remains above3; no new crossing occurs after that touch.
    assert not [s for s in found if s.side == "BUY" and s.level == 3.6]


def test_bias_stories_do_not_publish_before_the_origin_close():
    origin, lower = prebroken_reference_case()
    found = bias.find_stories(origin, lower, origin_tf="H4", confirmation_tf="H1",
                              as_of=origin.index[-1])
    for story in found:
        assert story.available_at >= story.origin_at
        assert story.available_at >= story.confirmation_at
        assert story.reference_available_at < story.confirmation_at
        if story.target is not None:
            assert story.target_available_at <= story.available_at
            assert story.target_tf == story.origin_tf


def test_close_reference_is_explicit_and_does_not_interpolate_a_feed_gap():
    data = closed([(1.10, 1.21, 1.09, 1.20), (1.201, 1.22, 1.14, 1.15)])
    assert levels(data, as_of=data.index[-1]) == []
    found = levels(data, as_of=data.index[-1], level_mode="close_reference")
    assert len(found) == 1 and found[0].kind == "A"
    assert found[0].price == 1.20  # Never midpoint1.2005 or the new open1.201.
    assert found[0].available_at == data.index[1]
    assert levels(data.iloc[:1], as_of=data.index[0], level_mode="close_reference") == []
    # A bearish body wholly above the old close is not a sell-side turn at it.
    above = closed([(1.10, 1.21, 1.09, 1.20), (1.22, 1.23, 1.205, 1.21)])
    assert levels(above, as_of=above.index[-1], level_mode="close_reference") == []


def engulf_case():
    return closed([(1.10, 1.30, 1.00, 1.20), (1.20, 1.25, 1.05, 1.10),
                   (1.10, 1.30, 1.07, 1.25), (1.25, 1.32, 1.12, 1.20)])


def context(data, **changes):
    at = data.index[0] - pd.Timedelta(hours=1)
    return Context(**{"side": "BUY", "available_at": at, "origin_tf": "D",
                      "target": 1.4, "target_available_at": at,
                      "target_kind": "ORIGIN_KL", "target_tf": "D", **changes})


def test_setups_preserve_frozen_target_and_separate_stop_profiles():
    data = engulf_case()
    known = context(data)
    source = detect_setups(data, known, tf="H1", profile=RiskProfile("structural_wick", .0001),
                           as_of=data.index[-1], models=("engulf_retest",))
    fixed = detect_setups(data, known, tf="H1", profile=RiskProfile("fixed_pips", .0001),
                          as_of=data.index[-1], models=("engulf_retest",))
    assert len(source) == len(fixed) == 1
    assert source[0].target == fixed[0].target == 1.4
    assert source[0].target_kind == "ORIGIN_KL"  # Not invented nearest ERL.
    assert source[0].entry == fixed[0].entry == 1.10
    assert source[0].stop != fixed[0].stop
    assert source[0].available_at == fixed[0].available_at == data.index[2]
    assert source[0].context_available_at <= source[0].available_at


def test_setup_prefixes_do_not_change_and_future_context_cannot_retroactively_admit():
    data = engulf_case()
    profile = RiskProfile("structural_wick", .0001)
    full = detect_setups(data, context(data), tf="H1", profile=profile,
                          as_of=data.index[-1], models=("engulf_retest",))
    for n in range(1, len(data) + 1):
        now = data.index[n - 1]
        prefix = detect_setups(data.iloc[:n], context(data), tf="H1", profile=profile,
                                as_of=now, models=("engulf_retest",))
        assert prefix == [s for s in full if s.available_at <= now]
    future = context(data, available_at=data.index[-1] + pd.Timedelta(hours=1))
    assert detect_setups(data, future, tf="H1", profile=profile,
                          as_of=data.index[-1], models=("engulf_retest",)) == []


def test_a_later_found_target_cannot_rewrite_an_earlier_context():
    data = engulf_case()
    with pytest.raises(ValueError, match="before it is known"):
        context(data, target_available_at=data.index[1])


def test_paper_execution_cannot_fill_on_the_formation_bar():
    data = hourly([(1.1005, 1.1030, 1.0980, 1.1000),
                   (1.1005, 1.1010, 1.1002, 1.1005)], start="2026-01-05T09:00Z")
    got = simulate(order(), data, as_of="2026-01-05T11:00Z", costs=Costs(0, 0, 0))
    assert got["status"] == "PENDING" and got["fill_price"] is None


def test_paper_execution_uses_ask_for_buy_fill_and_sell_stop():
    data = hourly([(1.1005, 1.1010, 1.0999, 1.1004)])
    assert simulate(order(), data, as_of="2026-01-05T11:00Z", costs=Costs(2, 0, 0))["status"] == "PENDING"
    assert simulate(order(), data, as_of="2026-01-05T11:00Z", costs=Costs(0, 0, 0))["status"] == "FILLED"
    sell = order(side="SELL", stop=1.1010, target=1.0980, bias_side="SELL")
    data = hourly([(1.1000, 1.1009, 1.0995, 1.1001)])
    costly = simulate(sell, data, as_of="2026-01-05T11:00Z", costs=Costs(2, 0, 0))
    free = simulate(sell, data, as_of="2026-01-05T11:00Z", costs=Costs(0, 0, 0))
    assert costly["outcome"] == "LOSS" and free["outcome"] == "OPEN"


def test_commission_is_roundtrip_once_and_spread_not_subtracted_twice():
    data = hourly([(1.1005, 1.1010, 1.0999, 1.1002),
                   (1.1002, 1.1021, 1.1001, 1.1015)])
    got = simulate(order(), data, as_of="2026-01-05T12:00Z", costs=Costs(1, 0, 2))
    assert got["outcome"] == "WIN"
    assert got["net_r"] == pytest.approx(1.8)
    assert got["time"] == "2026-01-05T11:00:00+00:00"
    assert got["fill_window"] == {"start": "2026-01-05T10:00:00+00:00", "end": got["time"]}


def test_gap_stop_executes_adversely_with_slippage_and_once_only_commission():
    data = hourly([(1.1005, 1.1010, 1.0999, 1.1002),
                   (1.0987, 1.1001, 1.0985, 1.0995)])
    got = simulate(order(), data, as_of="2026-01-05T12:00Z", costs=Costs(1, 2, 2))
    assert got["outcome"] == "LOSS"
    assert got["exit_price"] == pytest.approx(1.0985)
    assert got["net_r"] == pytest.approx(-1.7)


def test_fill_bar_target_is_censored_and_both_hit_remains_stop_first():
    data = hourly([(1.1005, 1.1025, 1.0999, 1.1010)])
    got = simulate(order(), data, as_of="2026-01-05T11:00Z", costs=Costs(0, 0, 0))
    assert got["status"] == "FILLED" and got["outcome"] == "CENSORED" and got["net_r"] is None
    both = hourly([(1.1005, 1.1025, 1.0985, 1.1010)])
    stopped = simulate(order(), both, as_of="2026-01-05T11:00Z", costs=Costs(0, 0, 0))
    assert stopped["outcome"] == "LOSS"
    assert any("stop-first" in flag for flag in stopped["flags"])


def test_missing_active_market_hour_censors_before_any_later_fill():
    data = hourly([(1.1005, 1.1010, 1.0999, 1.1002)], start="2026-01-05T11:00Z")
    got = simulate(order(), data, as_of="2026-01-05T12:00Z", costs=Costs(0, 0, 0))
    assert got["status"] == "CENSORED" and got["fill_price"] is None
    assert any("missing market hour" in flag for flag in got["flags"])


def test_partial_hour_availability_cannot_silently_skip_an_unseen_initial_fill():
    data = hourly([(1.1005, 1.1010, 1.0999, 1.1002)], start="2026-01-05T11:00Z")
    got = simulate(order(available_at="2026-01-05T10:30Z"), data,
                   as_of="2026-01-05T12:00Z", costs=Costs(0, 0, 0))
    assert got["outcome"] == "CENSORED" and got["fill_price"] is None

