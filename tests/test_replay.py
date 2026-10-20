"""Independent acceptance checks: full teacher matches, never nearest-price substitutes."""
from copy import deepcopy
import pytest

from bishop.replay import check_example, evaluate, validate_examples


def example():
    return {
        "id": "synthetic-checker-contract-not-teacher-evidence",
        "verification": "verified", "kind": "trade",
        "pair": "EURUSD", "side": "BUY", "tf": "H1", "mode": "zone_edge",
        "bias": {"side": "BUY", "tf": "D"},
        "setup_time": {"start": "2026-01-02T08:00:00Z", "end": "2026-01-02T09:00:00Z"},
        "time": {"start": "2026-01-02T10:00:00Z", "end": "2026-01-02T11:00:00Z"},
        "entry": 1.10, "stop": 1.09, "target": 1.13,
        "tolerances": {"entry": 0.0, "stop": 0.0, "target": 0.0},
        "evidence": [{"path": "tests/test_replay.py", "note": "Synthetic checker test only"}],
        "unresolved_reasons": [],
    }


def candidate(**changes):
    return {
        "pair": "EURUSD", "side": "BUY", "tf": "H1", "mode": "zone_edge",
        "bias": {"side": "BUY", "tf": "D"}, "setup_time": "2026-01-02T08:30:00Z",
        "time": "2026-01-02T10:30:00Z", "status": "FILLED",
        "entry": 1.10, "stop": 1.09, "target": 1.13,
        **changes,
    }


def document(*examples):
    return {"schema_version": 1, "examples": list(examples)}


def test_complete_match_passes_without_mutating_observations():
    ex, rows = example(), [candidate()]
    before = deepcopy((ex, rows))
    assert validate_examples(document(ex)) == []
    assert check_example(ex, rows)["status"] == "PASS"
    assert (ex, rows) == before
    assert evaluate(document(ex), rows)["status"] == "PASS"


@pytest.mark.parametrize("changes", [
    {"pair": "GBPUSD"}, {"side": "SELL"}, {"tf": "H2"}, {"mode": "fixed"},
    {"bias": {"side": "SELL", "tf": "D"}}, {"bias": {"side": "BUY", "tf": "W"}},
    {"bias": None}, {"setup_time": None},
    {"setup_time": "2026-01-02T07:59:59Z"}, {"setup_time": "2026-01-02T09:00:01Z"},
    {"time": "2026-01-02T09:59:59Z"}, {"time": "2026-01-02T11:00:01Z"},
    {"entry": 1.10001}, {"stop": 1.08999}, {"target": 1.13001},
    {"status": "PENDING"}, {"status": "MISSED"},
    {"entry": float("nan")}, {"stop": float("inf")}, {"target": None},
])
def test_each_required_dimension_is_independently_enforced(changes):
    result = check_example(example(), [candidate(**changes)])
    assert result["status"] == "FAIL"
    assert result["reasons"]


def test_absent_candidate_is_not_a_match():
    assert check_example(example(), [])["status"] == "FAIL"


def test_all_dimensions_must_match_one_candidate_not_collectively():
    rows = [candidate(stop=1.08), candidate(entry=1.11), candidate(target=1.14)]
    assert check_example(example(), rows)["status"] == "FAIL"


def test_any_complete_match_wins_over_closer_but_invalid_candidate():
    ex = example()
    ex["tolerances"] = {"entry": 0.001, "stop": 0.001, "target": 0.001}
    rows = [candidate(target=1.15), candidate(entry=1.1001, stop=1.0901, target=1.1301)]
    assert check_example(ex, rows)["status"] == "PASS"


def test_only_explicit_source_price_tolerances_apply():
    ex = example()
    ex["tolerances"] = {"entry": 0.0002, "stop": 0.0001, "target": 0.0003}
    assert check_example(ex, [candidate(entry=1.1001, stop=1.09005, target=1.1302)])["status"] == "PASS"
    assert check_example(ex, [candidate(target=1.1304)])["status"] == "FAIL"


@pytest.mark.parametrize("verification", ["partial", "unresolved"])
def test_incomplete_source_never_passes_even_if_prices_match(verification):
    ex = example()
    ex["verification"] = verification
    ex["unresolved_reasons"] = ["Frame price unreadable"]
    assert check_example(ex, [candidate()])["status"] == "UNRESOLVED"
    assert evaluate(document(ex), [candidate()])["status"] == "UNRESOLVED"


def test_verified_and_unresolved_coverage_cannot_be_presented_as_complete():
    ex2 = example()
    ex2.update(id="unresolved-source", verification="unresolved", entry=None,
               unresolved_reasons=["Entry unreadable"])
    result = evaluate(document(example(), ex2), [candidate()])
    assert result["status"] != "PASS"
    assert len(result["results"]) == 2


@pytest.mark.parametrize("change", [
    {"entry": None}, {"stop": float("nan")}, {"target": float("inf")},
    {"tolerances": {}}, {"tolerances": {"entry": -0.1, "stop": 0, "target": 0}},
    {"tolerances": {"entry": 0, "stop": 0, "target": float("nan")}},
    {"evidence": []},
    {"time": {"start": "2026-01-02T10:00:00", "end": "2026-01-02T11:00:00"}},
    {"time": {"start": "2026-01-03T10:00:00Z", "end": "2026-01-02T11:00:00Z"}},
    {"side": "SIDEWAYS"}, {"stop": 1.12}, {"target": 1.08},
    {"bias": None}, {"bias": {"side": "BUY"}},
    {"bias": {"side": "SIDEWAYS", "tf": "D"}},
    {"setup_time": None},
    {"setup_time": {"start": "2026-01-02T09:00:00Z", "end": "2026-01-02T08:00:00Z"}},
])
def test_invalid_verified_observation_rejected(change):
    ex = example()
    ex.update(change)
    assert validate_examples(document(ex))


def test_duplicate_fixture_ids_rejected():
    assert validate_examples(document(example(), example()))


def test_empty_example_set_is_not_success():
    assert evaluate(document(), [candidate()])["status"] != "PASS"


def test_no_trade_requires_explicit_observation_and_rejects_actual_fill():
    ex = example()
    ex.update(kind="no_trade", entry=None, stop=None, target=None)
    observed = candidate(status="NO_TRADE", entry=None, stop=None, target=None)
    assert check_example(ex, [observed])["status"] == "PASS"
    assert check_example(ex, [])["status"] != "PASS"
    assert check_example(ex, [observed, candidate()])["status"] == "FAIL"


def test_stop_profile_cannot_relabel_owner_override_as_teacher_match():
    ex = example()
    assert check_example(ex, [candidate(mode="fixed_10_pips")])["status"] == "FAIL"


def test_zero_tolerance_does_not_hide_small_price_difference():
    assert check_example(example(), [candidate(entry=1.10 + 1e-13)])["status"] == "FAIL"


def test_verified_label_does_not_erase_unresolved_source_questions():
    ex = example()
    ex["unresolved_reasons"] = ["Target cannot actually be read"]
    assert validate_examples(document(ex))
    assert check_example(ex, [candidate()])["status"] != "PASS"


def test_no_trade_fill_cannot_hide_on_another_timeframe_or_stop_profile():
    ex = example()
    ex.update(kind="no_trade", entry=None, stop=None, target=None)
    observed = candidate(status="NO_TRADE", entry=None, stop=None, target=None)
    assert check_example(ex, [observed, candidate(tf="H2", mode="fixed_10_pips")])["status"] == "FAIL"


@pytest.mark.parametrize("status", ["PENDING", "TRIGGERED", "APPROVED"])
def test_no_trade_prohibits_actionable_orders_even_before_fill(status):
    ex = example()
    ex.update(kind="no_trade", entry=None, stop=None, target=None)
    observed = candidate(status="NO_TRADE", entry=None, stop=None, target=None)
    assert check_example(ex, [observed, candidate(status=status)])["status"] == "FAIL"


def test_no_trade_malformed_same_pair_clock_cannot_hide_an_order():
    ex = example()
    ex.update(kind="no_trade", entry=None, stop=None, target=None)
    observed = candidate(status="NO_TRADE", entry=None, stop=None, target=None)
    assert check_example(ex, [observed, candidate(time="unknown")])["status"] == "FAIL"


def test_cli_returns_failure_for_unresolved_fixture(tmp_path):
    import json
    import subprocess
    import sys

    ex = example()
    ex.update(verification="unresolved", unresolved_reasons=["Chart date unreadable"])
    examples_path, observations_path, report_path = (tmp_path / name for name in ("examples.json", "observations.json", "report.json"))
    examples_path.write_text(json.dumps(document(ex)))
    observations_path.write_text(json.dumps([candidate()]))
    proc = subprocess.run([sys.executable, "-m", "bishop.replay", "--examples", str(examples_path),
                           "--observations", str(observations_path), "--out", str(report_path)],
                          capture_output=True, text=True)
    assert proc.returncode != 0
    assert json.loads(report_path.read_text())["status"] == "UNRESOLVED"


def test_setup_must_have_been_available_before_fill_even_with_broad_source_window():
    ex = example()
    ex["setup_time"] = {"start": "2026-01-02T08:00:00Z", "end": "2026-01-02T12:00:00Z"}
    assert check_example(ex, [candidate(setup_time="2026-01-02T11:00:00Z")])["status"] == "FAIL"


def test_no_trade_observation_does_not_require_trade_only_bias_and_setup_fields():
    ex = example()
    ex.update(kind="no_trade", entry=None, stop=None, target=None)
    ex.pop("bias")
    ex.pop("setup_time")
    observed = candidate(status="NO_TRADE", entry=None, stop=None, target=None)
    observed.pop("bias")
    observed.pop("setup_time")
    assert check_example(ex, [observed])["status"] == "PASS"
