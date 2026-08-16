import csv
import os
import tempfile

from .. import report as report_module
from ..report import _summarize_rows, _svg_equity_curve, _trades_table_html, generate_report


def test_summarize_rows_computes_win_rate_and_total_r():
    rows = [
        {"status": "closed_win", "r_multiple": "3.0"},
        {"status": "closed_win", "r_multiple": "3.0"},
        {"status": "closed_loss", "r_multiple": "-1.0"},
        {"status": "open", "r_multiple": ""},
    ]
    stats = _summarize_rows(rows)
    assert stats["total_trades"] == 4
    assert stats["closed_trades"] == 3
    assert stats["wins"] == 2
    assert abs(stats["win_rate"] - 2 / 3) < 1e-9
    assert stats["total_r"] == 5.0


def test_summarize_rows_handles_no_closed_trades():
    stats = _summarize_rows([{"status": "open", "r_multiple": ""}])
    assert stats["win_rate"] is None
    assert stats["avg_r"] is None


def test_svg_equity_curve_empty_shows_placeholder():
    assert "No closed trades" in _svg_equity_curve([])


def test_svg_equity_curve_renders_polyline_for_real_data():
    svg = _svg_equity_curve([3.0, -1.0, 3.0])
    assert "<polyline" in svg
    assert "<svg" in svg


def test_generate_report_builds_index_and_copies_csvs():
    with tempfile.TemporaryDirectory() as tmp:
        results_dir = os.path.join(tmp, "results")
        os.makedirs(results_dir)
        csv_path = os.path.join(results_dir, "EURUSD_conservative.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["status", "r_multiple"])
            writer.writeheader()
            writer.writerow({"status": "closed_win", "r_multiple": "3.0"})
            writer.writerow({"status": "closed_loss", "r_multiple": "-1.0"})

        out_dir = os.path.join(tmp, "site")
        out_path = generate_report(results_dir=results_dir, out_dir=out_dir)

        assert os.path.exists(out_path)
        with open(out_path) as f:
            html = f.read()
        assert "EURUSD_conservative" in html
        assert "50.0%" in html  # 1 win / 2 closed

        assert os.path.exists(os.path.join(out_dir, "results", "EURUSD_conservative.csv"))


def test_generate_report_handles_no_results_yet():
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = os.path.join(tmp, "site")
        out_path = generate_report(results_dir=os.path.join(tmp, "nonexistent"), out_dir=out_dir)
        with open(out_path) as f:
            html = f.read()
        assert "No results yet" in html


def test_generate_report_includes_trade_reasoning_table():
    with tempfile.TemporaryDirectory() as tmp:
        results_dir = os.path.join(tmp, "results")
        os.makedirs(results_dir)
        csv_path = os.path.join(results_dir, "EURUSD_conservative.csv")
        fieldnames = [
            "entry_time", "direction", "bias_daily", "bias_h4", "bias_h1",
            "effective_bias_timeframe", "entry_pattern", "trade_kind", "trigger_type",
            "aligned_timeframes", "key_level_shape", "key_level_price", "qmr_test_count",
            "imbalance_overlap", "stop_kind", "entry_price", "stop_loss",
            "primary_target", "status", "exit_reason", "r_multiple",
        ]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow({
                "entry_time": "2024-01-05T10:00:00", "direction": "bullish",
                "bias_daily": "bullish", "bias_h4": "bullish", "bias_h1": "bullish",
                "effective_bias_timeframe": "Daily", "entry_pattern": "direct_mitigation",
                "trade_kind": "continuation", "trigger_type": "engulfing",
                "aligned_timeframes": "Daily,H4", "key_level_shape": "V",
                "key_level_price": "1.1020", "qmr_test_count": "2",
                "imbalance_overlap": "True", "stop_kind": "engulfing",
                "entry_price": "1.1030", "stop_loss": "1.0994",
                "primary_target": "1.1138", "status": "closed_win",
                "exit_reason": "target_hit", "r_multiple": "3.0",
            })

        out_dir = os.path.join(tmp, "site")
        out_path = generate_report(results_dir=results_dir, out_dir=out_dir)
        with open(out_path) as f:
            html = f.read()

        assert "Trade-by-trade reasoning" in html
        assert "direct_mitigation" in html
        assert "trigger: engulfing" in html
        assert "aligned: Daily,H4" in html
        assert "QMR 2" in html
        assert "FVG overlap" in html
        assert "+3.00R" in html


def test_generate_report_renders_older_csvs_missing_the_newer_columns():
    # trigger_type/aligned_timeframes (entry-gate rebuild) didn't exist on
    # CSVs from earlier runs -- the reasoning row must degrade gracefully
    # (a "—" placeholder) rather than erroring on the missing columns.
    with tempfile.TemporaryDirectory() as tmp:
        results_dir = os.path.join(tmp, "results")
        os.makedirs(results_dir)
        csv_path = os.path.join(results_dir, "EURUSD_conservative.csv")
        fieldnames = ["entry_time", "direction", "entry_pattern", "trade_kind",
                      "status", "exit_reason", "r_multiple"]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow({
                "entry_time": "2024-01-05T10:00:00", "direction": "bullish",
                "entry_pattern": "direct_mitigation", "trade_kind": "continuation",
                "status": "closed_win", "exit_reason": "target_hit", "r_multiple": "3.0",
            })

        out_dir = os.path.join(tmp, "site")
        out_path = generate_report(results_dir=results_dir, out_dir=out_dir)
        with open(out_path) as f:
            html = f.read()

        assert "trigger: —" in html
        assert "aligned: —" in html


def test_trades_table_caps_display_and_shows_note(monkeypatch):
    monkeypatch.setattr(report_module, "MAX_TRADES_DISPLAYED", 2)
    rows = [{"entry_time": f"t{i}", "status": "closed_win", "r_multiple": "1.0"} for i in range(5)]
    html = _trades_table_html(rows)
    assert "Showing the most recent 2 of 5 trades" in html


def test_trades_table_empty_for_no_rows():
    assert _trades_table_html([]) == ""
