"""Execution lifecycle and batch equivalence beyond the independent review cases."""
import pandas as pd
import pytest

from bishop.execution import Costs, simulate, simulate_many
from test_engine_review import order, hourly


def untouched():
    return hourly([(1.1005, 1.1010, 1.1002, 1.1005)] * 3)


def test_pending_cancellation_prevents_future_fill_and_prior_expiry_wins():
    data = untouched()
    data.loc[data.index[2], "low"] = 1.0999
    cancelled = simulate(order(cancel_at="2026-01-05T12:00Z"), data,
                         as_of="2026-01-05T13:00Z", costs=Costs(0, 0, 0))
    assert cancelled["status"] == "CANCELLED" and cancelled["time"] is None
    expired = simulate(order(expires_at="2026-01-05T11:00Z", cancel_at="2026-01-05T12:00Z"), data,
                       as_of="2026-01-05T13:00Z", costs=Costs(0, 0, 0))
    assert expired["status"] == "MISSED" and expired["outcome"] == "EXPIRED"


def test_partial_expiry_does_not_invent_a_fill_or_miss_from_the_whole_bar():
    data = hourly([(1.1005, 1.101, 1.0999, 1.1002)])
    result = simulate(order(expires_at="2026-01-05T10:30Z"), data,
                      as_of="2026-01-05T11:00Z", costs=Costs(0, 0, 0))
    assert result["status"] == "CENSORED" and result["fill_price"] is None


def test_subhour_cancellation_before_the_first_bar_closes_cannot_erase_a_possible_fill():
    data = untouched().iloc[:0]
    result = simulate(order(cancel_at="2026-01-05T10:30Z"), data,
                      as_of="2026-01-05T10:45Z", costs=Costs(0, 0, 0))
    assert result["status"] == "CENSORED" and result["fill_price"] is None


def test_filled_position_keeps_own_exit_after_pending_expiry_or_cancellation():
    data = hourly([(1.1005, 1.1010, 1.0999, 1.1002), (1.1002, 1.1021, 1.1001, 1.1015)])
    result = simulate(order(expires_at="2026-01-05T11:00Z", cancel_at="2026-01-05T11:00Z"), data,
                      as_of="2026-01-05T12:00Z", costs=Costs(0, 0, 0))
    assert result["status"] == "FILLED" and result["outcome"] == "WIN"


def test_gap_after_known_fill_censors_return_without_erasing_the_known_fill():
    data = hourly([(1.1005, 1.1010, 1.0999, 1.1002)])
    result = simulate(order(), data, as_of="2026-01-05T12:00Z", costs=Costs(0, 0, 0))
    assert result["status"] == "FILLED" and result["outcome"] == "CENSORED"
    assert result["net_r"] is None


def test_batch_is_identical_to_individual_orders_with_distinct_lifecycles():
    data = untouched()
    orders = [order(), order(id="expired", expires_at="2026-01-05T11:00Z"),
              order(id="cancelled", cancel_at="2026-01-05T11:00Z"),
              order(id="future", available_at="2026-01-05T14:00Z"),
              order(id="subhour", available_at="2026-01-05T10:30Z")]
    costs = Costs(1, .2, .5)
    one = [simulate(o, data, as_of="2026-01-05T13:00Z", costs=costs) for o in orders]
    many = simulate_many(orders, data, as_of="2026-01-05T13:00Z", costs=costs)
    assert one == many


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True])
def test_cost_assumptions_cannot_be_missing_negative_or_nonfinite(bad):
    with pytest.raises(ValueError): Costs(bad, 0, 0)
