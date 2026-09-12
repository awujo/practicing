"""
Standalone staleness watchdog for the live candle cache.

Motivation (operator, 2026-09-12, after the 2026-09-11 incident report's
52-hour-stale XAGUSD signal): every stale-candle problem so far was found
AFTER THE FACT -- by reading a Telegram log of a bad entry attempt, or by
checking by hand. This is the reverse: a direct, periodic check of "is the
cache actually current," alerting BEFORE a stale candle has a chance to
produce a bad decision.

NOT a fix for staleness -- a smoke detector, not a sprinkler system. What
actually reduces how OFTEN candles go stale is the caching fix and the
still-open algorithmic-cost work (see OPERATIONS_LOG.md, 2026-09-11/12).
This only makes sure nobody has to notice the next one by hand.

Deliberately a SEPARATE process (meant to be cron-fired), not a method
bolted onto LiveBot/orchestrator.py: if a hung or crash-looping live bot
process is exactly what caused the staleness, a watchdog living inside
that same struggling process could get stuck right along with it. This
reads the cache files directly and holds no MT5 connection at all, so it
keeps working regardless of what state the live bots are in.

Usage (VPS, cron-fired every 15-30 minutes -- see bot/README.md):
    docker exec -u abc -w /config/trading mt5 python3 -m bot.check_staleness \\
        --instruments EURUSD,GBPUSD,... --max-staleness-minutes 90
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from backtest.data_pipeline import cache
from .telegram_notify import send_message

# Mirrors orchestrator.LiveBot's own weekend-close rule exactly (same
# zone, same weekday/hour) -- duplicated rather than imported so this
# watchdog does not have to pull in orchestrator.py's MT5-facing imports
# (mt5_data, mt5_execution) just to reuse one small pure function.
WEEKEND_CLOSE_ZONE = ZoneInfo("America/New_York")
WEEKEND_CLOSE_WEEKDAY = 4   # Friday
WEEKEND_CLOSE_LOCAL_HOUR = 17


def _market_closed_for_weekend(now: datetime) -> bool:
    local = now.astimezone(WEEKEND_CLOSE_ZONE)
    after_friday_close = (local.weekday() == WEEKEND_CLOSE_WEEKDAY
                          and local.hour >= WEEKEND_CLOSE_LOCAL_HOUR)
    saturday = local.weekday() == 5
    sunday_before_open = local.weekday() == 6 and local.hour < WEEKEND_CLOSE_LOCAL_HOUR
    return after_friday_close or saturday or sunday_before_open


def _expected_latest_open_time(now: datetime) -> pd.Timestamp:
    """The open time of the most recently CLOSED H1 bar, as of `now`.
    MT5/dukascopy candle `time` is the bar's OPEN, so the bar opening at
    e.g. 14:00 is only complete once 15:00 arrives."""
    floored = now.replace(minute=0, second=0, microsecond=0)
    return pd.Timestamp(floored - timedelta(hours=1))


def check(instruments: list[str], source: str, max_staleness_minutes: float,
          now: datetime | None = None) -> list[tuple[str, float | None, str]]:
    """Returns (instrument, staleness_minutes, detail) for every
    instrument staler than allowed. staleness_minutes is None when there
    is no cache to even measure staleness from (detail explains why).
    Always empty while the market is closed for the weekend -- nothing
    SHOULD be arriving then, so silence there is correct, not a miss.
    """
    now = now or datetime.now(timezone.utc)
    if _market_closed_for_weekend(now):
        return []

    expected = _expected_latest_open_time(now)
    stale = []
    for instrument in instruments:
        try:
            last = cache.last_cached_time(source, instrument, "H1")
        except Exception as exc:
            stale.append((instrument, None, f"cache unreadable: {exc}"))
            continue
        if last is None:
            stale.append((instrument, None, "no cache at all"))
            continue
        last_ts = pd.Timestamp(last)
        staleness_minutes = (expected - last_ts).total_seconds() / 60
        if staleness_minutes > max_staleness_minutes:
            stale.append((instrument, staleness_minutes, str(last_ts)))
    return stale


def _format_report(stale: list[tuple[str, float | None, str]]) -> str:
    lines = [f"\U0001F6A8 STALE CANDLE CACHE -- {len(stale)} instrument(s):"]
    for instrument, minutes, detail in stale:
        if minutes is None:
            lines.append(f"  {instrument}: {detail}")
        else:
            lines.append(f"  {instrument}: {minutes:.0f} min stale (last cached candle: {detail})")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True, help="comma-separated, e.g. EURUSD,GBPUSD,XAUUSD")
    parser.add_argument("--source", default="dukascopy")
    parser.add_argument("--max-staleness-minutes", type=float, default=90.0,
                         help="alert once the newest cached H1 candle is older than this many "
                              "minutes past when the most recently closed H1 bar should be. "
                              "90 (default) tolerates one full candle of ordinary sync lag plus "
                              "buffer without false-alarming on normal operation.")
    args = parser.parse_args()

    instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    stale = check(instruments, args.source, args.max_staleness_minutes)

    if not stale:
        print(f"all {len(instruments)} instruments current")
        return

    text = _format_report(stale)
    print(text)

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        send_message(token, chat_id, text)
    else:
        print("(TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set in this process's environment -- "
              "not sent to Telegram, see this command's own -e flags)")


if __name__ == "__main__":
    main()
