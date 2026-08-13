"""
Thin wrapper around the Oanda v20 REST API's candles endpoint.

Docs: https://developer.oanda.com/rest-live-v20/instrument-ep/

Handles the two things a single naive request can't:
- Oanda caps each response at 5000 candles, so multi-year history needs
  pagination -- we page forward using the last candle's own timestamp.
- Rate limiting / transient errors get retried with backoff rather than
  failing the whole run.
"""

import os
import time
from datetime import datetime, timezone

import requests

BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

MAX_CANDLES_PER_REQUEST = 5000
MAX_RETRIES = 5


def _api_key() -> str:
    key = os.environ.get("OANDA_API_KEY")
    if not key:
        raise RuntimeError(
            "OANDA_API_KEY not set. Copy backtest/data_pipeline/.env.example to "
            ".env, fill in your Oanda personal access token, and load it "
            "(e.g. `set -a; source .env; set +a`) before running the fetcher."
        )
    return key


def _base_url() -> str:
    env = os.environ.get("OANDA_ENVIRONMENT", "practice")
    if env not in BASE_URLS:
        raise RuntimeError(f"OANDA_ENVIRONMENT must be 'practice' or 'live', got {env!r}")
    return BASE_URLS[env]


def _request_with_retry(url: str, params: dict) -> dict:
    headers = {"Authorization": f"Bearer {_api_key()}"}
    delay = 2
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Oanda request failed after {MAX_RETRIES} attempts: {url}")


def fetch_candles(instrument: str, granularity: str, since: str | None = None,
                   until: datetime | None = None, price: str = "M") -> list[dict]:
    """
    Fetch candles for `instrument` at `granularity`, from `since` (exclusive,
    ISO-8601 string or None for "as far back as Oanda has") up to `until`
    (defaults to now). Pages automatically past the 5000-candle-per-request cap.

    Returns a list of dicts with keys: time, open, high, low, close, volume.
    Only *complete* candles are returned -- the still-forming current candle
    is dropped so the cache never stores a partial bar.
    """
    url = f"{_base_url()}/v3/instruments/{instrument}/candles"
    until = until or datetime.now(timezone.utc)

    all_rows: list[dict] = []
    cursor = since

    while True:
        params = {"granularity": granularity, "price": price, "count": MAX_CANDLES_PER_REQUEST}
        if cursor:
            params["from"] = cursor
        else:
            # No prior cache: Oanda needs an explicit start; go back far
            # enough to capture full history for any granularity we use.
            params["from"] = "2005-01-01T00:00:00Z"

        data = _request_with_retry(url, params)
        candles = data.get("candles", [])
        if not candles:
            break

        page_rows = [
            {
                "time": c["time"],
                "open": float(c["mid"]["o"]),
                "high": float(c["mid"]["h"]),
                "low": float(c["mid"]["l"]),
                "close": float(c["mid"]["c"]),
                "volume": int(c["volume"]),
            }
            for c in candles
            if c.get("complete")
        ]
        all_rows.extend(page_rows)

        last_time = candles[-1]["time"]
        last_dt = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
        if last_dt >= until or len(candles) < MAX_CANDLES_PER_REQUEST:
            break
        cursor = last_time

    return all_rows
