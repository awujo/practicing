import time
from unittest.mock import patch

import requests

from .. import app as app_module

app = app_module.app


def test_run_form_lists_known_instruments():
    with app.test_client() as c:
        resp = c.get("/run")
    assert resp.status_code == 200
    assert b"EURUSD" in resp.data
    assert b"USDCAD" in resp.data


def test_run_start_rejects_unknown_instrument():
    with app.test_client() as c:
        resp = c.post("/run/start", data={"instrument": "NOTREAL", "style": "conservative"})
    assert resp.status_code == 400


def test_run_start_dispatches_and_redirects_to_a_status_token():
    with patch.object(app_module.data_access, "run_backtest_dispatch", return_value=12345.0) as mock_dispatch, \
         app.test_client() as c:
        resp = c.post("/run/start", data={"instrument": "EURUSD", "style": "conservative", "year": "2026"})

    assert resp.status_code == 302
    assert resp.location.startswith("/run/status/")
    mock_dispatch.assert_called_once_with("EURUSD", "conservative", year=2026, rr=None)

    token = resp.location.rsplit("/", 1)[-1]
    assert token in app_module._pending_runs
    assert app_module._pending_runs[token]["result_name"] == "EURUSD_conservative_2026"


def test_run_start_accepts_ratio_notation_for_rr():
    with patch.object(app_module.data_access, "run_backtest_dispatch", return_value=12345.0) as mock_dispatch, \
         app.test_client() as c:
        resp = c.post("/run/start", data={"instrument": "EURUSD", "style": "conservative", "rr": "3:1"})

    assert resp.status_code == 302
    mock_dispatch.assert_called_once_with("EURUSD", "conservative", year=None, rr=3.0)
    token = resp.location.rsplit("/", 1)[-1]
    del app_module._pending_runs[token]


def test_run_start_shows_a_friendly_error_for_unparseable_rr():
    with app.test_client() as c:
        resp = c.post("/run/start", data={"instrument": "EURUSD", "style": "conservative", "rr": "nonsense"})

    assert resp.status_code == 400
    assert b"Couldn&#39;t parse" in resp.data or b"parse" in resp.data


def test_run_start_shows_a_friendly_error_when_dispatch_fails_instead_of_500ing():
    error = requests.exceptions.HTTPError("403 Client Error: Forbidden")
    with patch.object(app_module.data_access, "run_backtest_dispatch", side_effect=error), \
         app.test_client() as c:
        resp = c.post("/run/start", data={"instrument": "EURUSD", "style": "conservative"})

    assert resp.status_code == 502
    assert b"Couldn" in resp.data
    assert b"actions:write" in resp.data


def test_run_status_shows_a_friendly_error_when_polling_fails_instead_of_500ing():
    token = "test-token-err"
    app_module._pending_runs[token] = {
        "instrument": "EURUSD", "style": "conservative", "year": None, "rr": None,
        "triggered_at": time.time(), "run_id": 999,
        "result_name": "EURUSD_conservative",
    }
    error = requests.exceptions.HTTPError("404 Client Error: Not Found")
    with patch.object(app_module.data_access, "get_workflow_run", side_effect=error), \
         app.test_client() as c:
        resp = c.get(f"/run/status/{token}")

    assert resp.status_code == 502
    assert b"Couldn" in resp.data
    del app_module._pending_runs[token]


def test_run_status_unknown_token_404s():
    with app.test_client() as c:
        resp = c.get("/run/status/does-not-exist")
    assert resp.status_code == 404


def test_run_status_shows_queued_until_the_run_is_found():
    token = "test-token-1"
    app_module._pending_runs[token] = {
        "instrument": "EURUSD", "style": "conservative", "year": None, "rr": None,
        "triggered_at": time.time(), "run_id": None,
        "result_name": "EURUSD_conservative",
    }
    with patch.object(app_module.data_access, "find_dispatched_run", return_value=None), \
         app.test_client() as c:
        resp = c.get(f"/run/status/{token}")

    assert resp.status_code == 200
    assert b"Queued" in resp.data
    del app_module._pending_runs[token]


def test_run_status_shows_in_progress_once_the_run_is_found():
    token = "test-token-2"
    app_module._pending_runs[token] = {
        "instrument": "EURUSD", "style": "conservative", "year": None, "rr": None,
        "triggered_at": time.time(), "run_id": None,
        "result_name": "EURUSD_conservative",
    }
    found = {"id": 999, "html_url": "https://github.com/awujo/trading/actions/runs/999"}
    running = {"id": 999, "status": "in_progress", "conclusion": None, "html_url": found["html_url"]}
    with patch.object(app_module.data_access, "find_dispatched_run", return_value=found), \
         patch.object(app_module.data_access, "get_workflow_run", return_value=running), \
         app.test_client() as c:
        resp = c.get(f"/run/status/{token}")

    assert resp.status_code == 200
    assert b"in_progress" in resp.data
    assert app_module._pending_runs[token]["run_id"] == 999
    del app_module._pending_runs[token]


def test_run_status_links_to_results_once_the_run_succeeds():
    token = "test-token-3"
    app_module._pending_runs[token] = {
        "instrument": "EURUSD", "style": "conservative", "year": None, "rr": None,
        "triggered_at": time.time(), "run_id": 999,
        "result_name": "EURUSD_conservative",
    }
    done = {"id": 999, "status": "completed", "conclusion": "success",
            "html_url": "https://github.com/awujo/trading/actions/runs/999"}
    with patch.object(app_module.data_access, "get_workflow_run", return_value=done), \
         app.test_client() as c:
        resp = c.get(f"/run/status/{token}")

    assert resp.status_code == 200
    assert b"/results/EURUSD_conservative" in resp.data
    del app_module._pending_runs[token]


def test_run_status_shows_the_failure_link_when_the_run_fails():
    token = "test-token-4"
    app_module._pending_runs[token] = {
        "instrument": "EURUSD", "style": "conservative", "year": None, "rr": None,
        "triggered_at": time.time(), "run_id": 999,
        "result_name": "EURUSD_conservative",
    }
    failed = {"id": 999, "status": "completed", "conclusion": "failure",
              "html_url": "https://github.com/awujo/trading/actions/runs/999"}
    with patch.object(app_module.data_access, "get_workflow_run", return_value=failed), \
         app.test_client() as c:
        resp = c.get(f"/run/status/{token}")

    assert resp.status_code == 200
    assert b"failure" in resp.data
    del app_module._pending_runs[token]
