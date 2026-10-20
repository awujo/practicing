"""Real observation shape: pending orders have no invented fill timestamp."""
from bishop.replay import check_example
from test_replay import candidate, example


def test_pending_order_without_fill_time_cannot_mask_a_real_complete_fill():
    pending = candidate(status="PENDING", time=None, observed_at="2026-01-02T10:45:00Z")
    assert check_example(example(), [candidate(), pending])["status"] == "PASS"
    assert check_example(example(), [pending])["status"] == "FAIL"


def test_observation_clock_cannot_substitute_for_an_unknown_actual_fill_time():
    unproved_fill = candidate(time=None, observed_at="2026-01-02T10:45:00Z")
    assert check_example(example(), [unproved_fill])["status"] == "FAIL"


def test_no_trade_rejects_a_pending_order_observed_during_its_window():
    ex = example()
    ex.update(kind="no_trade", entry=None, stop=None, target=None)
    no_trade = candidate(status="NO_TRADE", entry=None, stop=None, target=None)
    pending = candidate(status="PENDING", time=None, observed_at="2026-01-02T10:45:00Z")
    assert check_example(ex, [no_trade, pending])["status"] == "FAIL"
