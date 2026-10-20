"""Frozen actual-feed integration, not teacher-fidelity or profitability tests."""
from pathlib import Path
import json
import subprocess
import sys
from dataclasses import replace

import pandas as pd
import pytest

from bishop.coverage import load_csv
from bishop.engine import run
from bishop.execution import Costs
from bishop import bias, candles, engine

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/examples/EURGBP_pdf_p08_icmarkets_bid_H1.csv.gz"


def configuration(clock):
    return dict(pair="EURGBP", as_of=clock, history_start="2026-06-01T00:00Z",
                scan_start="2026-06-01T00:00Z", origin_tf="D", entry_tf="H1",
                level_mode="close_reference", stop_profile="structural_wick",
                costs=Costs(1., .2, .5), pending_hours=24)


def test_actual_feed_run_is_reproducible_and_setup_events_are_prefix_causal():
    clock = pd.Timestamp("2026-07-24T00:00Z")
    frame, digest = load_csv(DATA, as_of=clock)
    full = run(frame, **configuration(clock))
    assert digest == "815f153eccb7ac981c06850bab82a5cd39dd41146810497f7b115d0839d559b0"
    assert full["status"] == "COMPUTED_SUPPORTED_ROUTES"
    assert full["coverage"]["missing_hours"] == 0
    assert full["summary"]["setups"] > 0 and full["summary"]["filled"] > 0
    for earlier in ("2026-07-10T00:00Z", "2026-07-22T00:00Z", "2026-07-23T18:00Z"):
        at = pd.Timestamp(earlier)
        prefix = frame[frame.index + pd.Timedelta(hours=1) <= at]
        observed = run(prefix, **configuration(at))
        assert observed["setups"] == [s for s in full["setups"] if pd.Timestamp(s["available_at"]) <= at]
        before = {r["id"]: r for r in observed["observations"] if r["time"] is not None}
        after = {r["id"]: r for r in full["observations"] if r["time"] is not None and pd.Timestamp(r["time"]) <= at}
        assert set(before) == set(after)
        for key in before:
            for field in ("entry", "stop", "target", "setup_time", "time", "fill_window", "bias"):
                assert before[key][field] == after[key][field]


def test_missing_warmup_hour_blocks_all_execution_instead_of_using_partial_cache():
    clock = "2026-07-24T00:00Z"
    frame, _ = load_csv(DATA, as_of=clock)
    partial = frame.drop(pd.Timestamp("2026-06-03T12:00Z"))
    result = run(partial, **configuration(clock))
    assert result["status"] == "INCOMPLETE_DATA"
    assert result["coverage"]["missing_hours"] == 1
    assert result["stories"] == result["setups"] == result["observations"] == []


def test_cli_exports_engine_observations_and_cannot_pass_unresolved_teacher_cases(tmp_path):
    target = tmp_path / "run.json"
    proc = subprocess.run([sys.executable, "-m", "bishop.backtest", "--data", str(DATA),
        "--source", "IC Markets cTrader alternate feed; source chart is FOREXCOM", "--pair", "EURGBP",
        "--as-of", "2026-07-24T00:00Z", "--history-start", "2026-06-01T00:00Z",
        "--scan-start", "2026-07-22T00:00Z", "--origin-tf", "D", "--entry-tf", "H2",
        "--level-mode", "close_reference", "--stop-profile", "structural_wick", "--spread-pips", "1",
        "--stop-slippage-pips", ".2", "--commission-pips", ".5", "--pending-hours", "24",
        "--examples", str(ROOT / "tests/bishop_examples.json"), "--out", str(target)],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 1
    result = json.loads(target.read_text())
    assert result["status"] == "COMPUTED_SUPPORTED_ROUTES"
    assert result["teacher_acceptance"]["status"] == "UNRESOLVED"
    assert result["input"]["sha256"]
    assert json.loads(target.with_name("run_observations.json").read_text()) == result["observations"]


def test_opposite_contexts_published_at_one_clock_cannot_automatically_place_orders(monkeypatch):
    clock = "2026-07-24T00:00Z"
    frame, _ = load_csv(DATA, as_of=clock)
    prefix = frame[frame.index >= pd.Timestamp("2026-06-01T00:00Z")]
    found = bias.find_stories(candles.completed(prefix, "D", clock), candles.completed(prefix, "H4", clock),
                              level_mode="close_reference", as_of=clock)
    story = next(s for s in found if s.target is not None)
    opposing = replace(story, side="SELL" if story.side == "BUY" else "BUY")
    monkeypatch.setattr(bias, "find_stories", lambda *a, **k: [story, opposing])
    def forbidden(*args, **kwargs):
        pytest.fail("ambiguous simultaneous directions must not enter pattern selection")
    monkeypatch.setattr(engine, "detect_setups", forbidden)
    result = run(frame, **configuration(clock))
    assert result["setups"] == result["observations"] == []
    assert len(result["skipped"]) == 2
    assert all(x["reason"] == "conflicting_opposite_contexts_at_same_clock" for x in result["skipped"])


def test_higher_entry_timeframe_cannot_skip_the_h1_confirmation_ladder():
    clock = "2026-07-24T00:00Z"
    frame, _ = load_csv(DATA, as_of=clock)
    cfg = configuration(clock)
    cfg.update(origin_tf="H4", entry_tf="H2")
    with pytest.raises(ValueError, match="only H1"):
        run(frame, **cfg)
