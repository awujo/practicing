"""
GitHub-backed data access for the on-demand trade-chart viewer.

Nothing here is baked in from a single backtest run -- every request
reads live from the repo's current GitHub state: the `data-latest`
release for candle data (published by fetch-data.yml), and whichever
trade-log CSVs run-backtest.yml has most recently published to the
`gh-pages` branch. That's deliberate -- it's what lets this viewer stay
current across every future backtest run (any instrument, any style)
without a redeploy, and it's also what lets the repo stay PRIVATE: this
is meant to run as a small server (Render, see render.yaml at the repo
root) that pulls the private repo server-side with a token, rather than
GitHub Pages, which would need the repo to go public to be viewable.

Two caches, refreshed independently:
  - the candle cache (the data-latest tarball) is large and changes at
    most daily (fetch-data.yml's schedule), so it's refreshed at most
    once per DATA_REFRESH_SECONDS;
  - published trade-log CSVs can change any time a backtest run
    finishes, so they're refreshed far more often (RESULTS_REFRESH_SECONDS)
    -- short enough that a just-published run shows up quickly, long
    enough that a burst of clicks on the same result set doesn't refetch
    on every request.

Also triggers new backtest runs (`run_backtest_dispatch()`): the webapp
itself never runs `run_backtest()` -- Render's free tier has tight
request timeouts and a single worker, wrong for a ~60-90s full-history
run blocking every other visitor. Instead it calls GitHub's
workflow_dispatch API to kick off the SAME `run-backtest.yml` used
throughout this project, which runs on GitHub's own infrastructure with
no timeout/RAM pressure, then polls for that run's status and links to
the (already-supported) results view once it publishes. This means
`GITHUB_TOKEN` needs `actions:write` (or classic PAT `repo` scope) on top
of the read access the rest of this module already needed -- if it's
missing, `run_backtest_dispatch()` fails with a 403/404 from GitHub, not
a silent no-op.
"""

import bisect
import csv
import io
import os
import tarfile
import threading
import time
from datetime import datetime

import requests

from ..data_pipeline import cache as cache_module
from ..engine.candles import load_candles

GITHUB_API = "https://api.github.com"
REPO = os.environ.get("GITHUB_REPO", "awujo/trading")
TOKEN = os.environ.get("GITHUB_TOKEN")
DATA_CACHE_DIR = os.environ.get("DATA_CACHE_DIR", "/tmp/slk-webapp-data")
DATA_REFRESH_SECONDS = int(os.environ.get("DATA_REFRESH_SECONDS", 3600))
RESULTS_REFRESH_SECONDS = int(os.environ.get("RESULTS_REFRESH_SECONDS", 60))

# The workflow whose workflow_dispatch inputs (instrument/style/year/rr)
# this drives -- see run_backtest_dispatch() below.
RUN_BACKTEST_WORKFLOW = "run-backtest.yml"

_data_lock = threading.Lock()
_instrument_fetched_at: dict[str, float] = {}

_results_cache: dict[str, tuple[float, list[dict]]] = {}
_results_cache_lock = threading.Lock()

_candles_cache: dict[tuple[str, str, str], tuple[float, list, list]] = {}
_candles_cache_lock = threading.Lock()


def _headers(accept: str = "application/vnd.github+json") -> dict:
    if not TOKEN:
        raise RuntimeError(
            "GITHUB_TOKEN is not set -- required to read the private "
            f"{REPO} repo (candle cache release + gh-pages results)."
        )
    return {"Authorization": f"token {TOKEN}", "Accept": accept}


def ensure_instrument_cache(instrument: str, source: str = "dukascopy") -> str:
    """Downloads/extracts just `instrument`'s own small per-instrument
    tar.gz asset from the data-latest release -- NOT the full ~260MB+
    all-instruments bundle (backtest-data.tar.gz), which is far too much
    to pull on every cold start on a small hosting tier (Render
    free/starter): that bundle alone is over the free tier's ~512MB RAM
    budget once downloaded, decompressed, and held alongside a Python/
    pandas/Flask process, and would very likely blow past Render's
    request timeout too. fetch-data.yml publishes one `{instrument}.tar.gz`
    asset per instrument alongside the full bundle specifically so this
    can stay small (see its "Package per-instrument data caches" step).

    Cached per instrument, at most once per DATA_REFRESH_SECONDS -- so
    viewing several different instruments in the same session downloads
    each one once, not the whole catalogue up front."""
    extracted_data_dir = os.path.join(DATA_CACHE_DIR, "data")
    instrument_dir = os.path.join(extracted_data_dir, source, instrument)

    with _data_lock:
        fetched_at = _instrument_fetched_at.get(instrument, 0.0)
        if os.path.isdir(instrument_dir) and (time.time() - fetched_at) < DATA_REFRESH_SECONDS:
            cache_module.DATA_ROOT = extracted_data_dir
            return extracted_data_dir

        resp = requests.get(f"{GITHUB_API}/repos/{REPO}/releases/tags/data-latest",
                             headers=_headers(), timeout=30)
        resp.raise_for_status()
        asset_name = f"{instrument}.tar.gz"
        asset = next((a for a in resp.json()["assets"] if a["name"] == asset_name), None)
        if asset is None:
            raise RuntimeError(
                f"data-latest release has no {asset_name} asset -- run the "
                "fetch-data.yml workflow first (it publishes one small "
                "per-instrument archive per instrument alongside the full cache)."
            )

        asset_resp = requests.get(asset["url"], headers=_headers(accept="application/octet-stream"), timeout=60)
        asset_resp.raise_for_status()

        os.makedirs(DATA_CACHE_DIR, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(asset_resp.content)) as tar:
            tar.extractall(DATA_CACHE_DIR)  # yields DATA_CACHE_DIR/data/{source}/{instrument}/...

        _instrument_fetched_at[instrument] = time.time()
        cache_module.DATA_ROOT = extracted_data_dir
        return extracted_data_dir


def load_candle_window(instrument: str, granularity: str, center_time, before: int, after: int,
                        source: str = "dukascopy") -> list:
    """The `before`/`after` candles around `center_time` for
    instrument/granularity, lazily loading and caching the full series in
    memory per (source, instrument, granularity) so repeated trade views
    against the same series don't re-read the CSV from disk every time."""
    ensure_instrument_cache(instrument, source)
    key = (source, instrument, granularity)

    with _candles_cache_lock:
        cached = _candles_cache.get(key)
    if cached is None or (time.time() - cached[0]) > DATA_REFRESH_SECONDS:
        candles = load_candles(source, instrument, granularity)
        times = [c.time for c in candles]
        with _candles_cache_lock:
            _candles_cache[key] = (time.time(), candles, times)
    else:
        _, candles, times = cached

    idx = bisect.bisect_left(times, center_time)
    start = max(0, idx - before)
    end = min(len(candles), idx + after)
    return candles[start:end]


def list_result_sets() -> list[str]:
    """Instrument_style names (e.g. 'EURUSD_conservative') currently
    published under results/ on the gh-pages branch."""
    resp = requests.get(f"{GITHUB_API}/repos/{REPO}/contents/results",
                         headers=_headers(), params={"ref": "gh-pages"}, timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return sorted(
        os.path.splitext(entry["name"])[0]
        for entry in resp.json()
        if entry["name"].endswith(".csv")
    )


def load_results(name: str) -> list[dict]:
    """Trade-log rows for `name`, fetched fresh from gh-pages and cached
    briefly (RESULTS_REFRESH_SECONDS)."""
    with _results_cache_lock:
        cached = _results_cache.get(name)
        if cached and (time.time() - cached[0]) < RESULTS_REFRESH_SECONDS:
            return cached[1]

    resp = requests.get(f"{GITHUB_API}/repos/{REPO}/contents/results/{name}.csv",
                         headers=_headers(accept="application/vnd.github.raw"),
                         params={"ref": "gh-pages"}, timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(resp.text)))

    with _results_cache_lock:
        _results_cache[name] = (time.time(), rows)
    return rows


def get_trade(name: str, trade_id: str) -> dict | None:
    for row in load_results(name):
        if row.get("trade_id") == str(trade_id):
            return row
    return None


def result_name_for(instrument: str, style: str, year: int | None = None, rr: float | None = None) -> str:
    """The result-set name (matching a gh-pages results/{name}.csv file)
    a `run_backtest_dispatch()` call with these same parameters will
    eventually publish. MUST stay in sync with runner.py's `main()` CLI
    suffix logic (year -> `_{year}`, rr -> `_rr{rr:g}`) -- duplicated
    here rather than imported since the webapp and the engine are
    separate deployable units (the webapp doesn't need the engine's own
    dependencies installed)."""
    suffix = f"_{year}" if year else ""
    if rr is not None:
        suffix += f"_rr{rr:g}"
    return f"{instrument}_{style}{suffix}"


def run_backtest_dispatch(instrument: str, style: str, year: int | None = None,
                           rr: float | None = None, ref: str = "main") -> float:
    """Triggers `run-backtest.yml` via workflow_dispatch with these
    inputs. Returns the trigger time (UTC epoch seconds) -- GitHub's
    dispatch API returns no run ID (a real API limitation), so the
    caller must separately poll `find_dispatched_run()` with this
    timestamp to find the run it just created."""
    inputs = {"instrument": instrument, "style": style}
    if year:
        inputs["year"] = str(year)
    if rr:
        inputs["rr"] = str(rr)
    resp = requests.post(
        f"{GITHUB_API}/repos/{REPO}/actions/workflows/{RUN_BACKTEST_WORKFLOW}/dispatches",
        headers=_headers(), json={"ref": ref, "inputs": inputs}, timeout=30,
    )
    resp.raise_for_status()
    return time.time()


def find_dispatched_run(triggered_at: float) -> dict | None:
    """One-shot lookup (no internal polling loop -- see the module
    docstring's request-timeout reasoning) for the newest workflow_dispatch
    run of `RUN_BACKTEST_WORKFLOW` created at/after `triggered_at` (minus a
    small buffer for clock skew between this server and GitHub's). Returns
    None if nothing matches yet -- the caller (the webapp's status page)
    re-calls this on each page auto-refresh until it resolves, rather than
    blocking a single request on it."""
    resp = requests.get(
        f"{GITHUB_API}/repos/{REPO}/actions/workflows/{RUN_BACKTEST_WORKFLOW}/runs",
        headers=_headers(), params={"event": "workflow_dispatch", "per_page": 5}, timeout=30,
    )
    resp.raise_for_status()
    buffer_seconds = 15
    for run in resp.json().get("workflow_runs", []):
        created_at = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).timestamp()
        if created_at >= triggered_at - buffer_seconds:
            return run
    return None


def get_workflow_run(run_id: int) -> dict:
    """Current status/conclusion/html_url for a specific run, for polling
    after `find_dispatched_run()` has located it."""
    resp = requests.get(f"{GITHUB_API}/repos/{REPO}/actions/runs/{run_id}",
                         headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()
