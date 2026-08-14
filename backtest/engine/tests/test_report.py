import csv
import os
import tempfile

from ..report import _summarize_rows, _svg_equity_curve, generate_report


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
