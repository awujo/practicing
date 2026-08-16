from unittest.mock import MagicMock, patch

from .. import data_access


def test_result_name_for_matches_cli_suffix_logic():
    assert data_access.result_name_for("EURUSD", "conservative") == "EURUSD_conservative"
    assert data_access.result_name_for("EURUSD", "conservative", year=2026) == "EURUSD_conservative_2026"
    assert data_access.result_name_for("EURUSD", "conservative", rr=4.0) == "EURUSD_conservative_rr4"
    assert data_access.result_name_for("EURUSD", "aggressive", year=2026, rr=4.0) == "EURUSD_aggressive_2026_rr4"


def test_run_backtest_dispatch_posts_the_expected_payload(monkeypatch):
    monkeypatch.setattr(data_access, "TOKEN", "dummy-token")
    mock_resp = MagicMock(status_code=204)
    mock_resp.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_resp) as mock_post:
        triggered_at = data_access.run_backtest_dispatch("EURUSD", "conservative", year=2026, rr=4.0)

    assert isinstance(triggered_at, float)
    url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
    assert url == f"{data_access.GITHUB_API}/repos/{data_access.REPO}/actions/workflows/run-backtest.yml/dispatches"
    assert kwargs["json"] == {"ref": "main", "inputs": {"instrument": "EURUSD", "style": "conservative",
                                                          "year": "2026", "rr": "4.0"}}


def test_run_backtest_dispatch_omits_blank_year_and_rr(monkeypatch):
    monkeypatch.setattr(data_access, "TOKEN", "dummy-token")
    mock_resp = MagicMock(status_code=204)
    mock_resp.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_resp) as mock_post:
        data_access.run_backtest_dispatch("EURUSD", "conservative")

    assert mock_post.call_args[1]["json"]["inputs"] == {"instrument": "EURUSD", "style": "conservative"}


def test_find_dispatched_run_returns_the_newest_matching_run(monkeypatch):
    monkeypatch.setattr(data_access, "TOKEN", "dummy-token")
    runs = [
        {"id": 3, "created_at": "2026-08-16T15:52:40Z", "html_url": "https://x/3"},
        {"id": 2, "created_at": "2026-08-16T15:37:57Z", "html_url": "https://x/2"},
        {"id": 1, "created_at": "2026-08-15T23:58:25Z", "html_url": "https://x/1"},
    ]
    mock_resp = MagicMock(status_code=200)
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"workflow_runs": runs}

    from datetime import datetime
    triggered_at = datetime.fromisoformat("2026-08-16T15:52:35+00:00").timestamp()

    with patch("requests.get", return_value=mock_resp):
        found = data_access.find_dispatched_run(triggered_at)

    assert found["id"] == 3


def test_find_dispatched_run_returns_none_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(data_access, "TOKEN", "dummy-token")
    runs = [{"id": 1, "created_at": "2020-01-01T00:00:00Z", "html_url": "https://x/1"}]
    mock_resp = MagicMock(status_code=200)
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"workflow_runs": runs}

    import time
    triggered_at = time.time()  # now -- way after that old run

    with patch("requests.get", return_value=mock_resp):
        found = data_access.find_dispatched_run(triggered_at)

    assert found is None


def test_get_workflow_run_returns_the_run_json(monkeypatch):
    monkeypatch.setattr(data_access, "TOKEN", "dummy-token")
    mock_resp = MagicMock(status_code=200)
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"id": 42, "status": "completed", "conclusion": "success"}

    with patch("requests.get", return_value=mock_resp) as mock_get:
        run = data_access.get_workflow_run(42)

    assert run == {"id": 42, "status": "completed", "conclusion": "success"}
    assert mock_get.call_args[0][0] == f"{data_access.GITHUB_API}/repos/{data_access.REPO}/actions/runs/42"
