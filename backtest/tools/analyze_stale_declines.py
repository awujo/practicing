"""
Answers a question about STALE_ENTRY_CUTOFF (bot/orchestrator.py) raised
by the operator 2026-09-15: "I thought it meant the setup has already
passed. Not that the confirmation showed up late."

STALE_ENTRY_CUTOFF is a CLOCK proxy -- it declines a market-order entry
once more than 3h have passed between the signal candle and the moment
its confirmation completes, on the theory that "market has likely moved
past this level." But it is only a proxy for that; the real, PRICE-based
answer already exists in setup_validity.check_setup() (built the same
week) and is already used on the limit-order path -- just never reached
for market orders, because the 3h gate declines BEFORE _consider_entry()
is ever called (see orchestrator.py's own comment on that ordering).

This script reads every decline_stale_signal row out of a live audit
database, replays the REAL H1 candles between the signal's entry_time
and the moment it was declined, and asks check_setup() what actually
happened to price in that window:

  - STOP_BREACHED / TARGET_ACHIEVED -> the clock agreed with price: the
    setup really was dead by the time it was declined.
  - ALIVE                           -> price was still intact. The bot
    threw away a still-tradeable setup purely for being old, not because
    the market had actually moved past it.

Deliberately does NOT touch check_setup()'s min_departure_r/limit-order
machinery -- market orders fill immediately at whatever price exists
now, so "ALIVE" here answers "was the level not yet invalidated",
matching STALE_ENTRY_CUTOFF's own stated intent, not "would a resting
limit have filled".

Usage (must run where the live audit database AND the live candle cache
both exist -- i.e. on the VPS, inside the container; a plain checkout
has neither):
    docker exec -u abc -w /config/trading mt5 python3 -m \\
        backtest.tools.analyze_stale_declines --db conservative_audit.db
    docker exec -u abc -w /config/trading mt5 python3 -m \\
        backtest.tools.analyze_stale_declines --db aggressive_audit.db
"""

import argparse
import sqlite3
from datetime import datetime, timezone

from backtest.engine.candles import load_candles
from backtest.engine.structure import Direction

from bot.setup_validity import Validity, check_setup


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fetch_stale_declines(db_path: str) -> list[dict]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT timestamp, instrument, entry_time, direction, entry_price, "
            "stop_loss, primary_target, entry_pattern, trigger_type FROM decisions "
            "WHERE event_type='entry_attempt' AND decision='decline_stale_signal' "
            "ORDER BY timestamp"
        )
        return [dict(r) for r in cur]
    finally:
        conn.close()


def evaluate(row: dict, source: str = "dukascopy"):
    """Returns a check_setup() ValidityVerdict, or None if the candle
    cache can't answer (missing/unreadable -- excluded from the report
    rather than guessed at, same "can't tell must mean can't tell" rule
    the rest of this codebase follows)."""
    try:
        h1 = load_candles(source, row["instrument"], "H1")
    except FileNotFoundError:
        return None
    signal_time = _parse_time(row["entry_time"])
    decline_time = _parse_time(row["timestamp"])
    candles_since = [c for c in h1 if signal_time < c.time <= decline_time]
    direction = Direction.BULLISH if row["direction"] == "bullish" else Direction.BEARISH
    return check_setup(row["entry_price"], row["stop_loss"], row["primary_target"],
                        direction, candles_since)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", required=True, help="path to the audit database, e.g. conservative_audit.db")
    parser.add_argument("--source", default="dukascopy")
    args = parser.parse_args()

    rows = fetch_stale_declines(args.db)
    print(f"{len(rows)} decline_stale_signal event(s) in {args.db}\n")

    counts = {Validity.ALIVE: 0, Validity.STOP_BREACHED: 0, Validity.TARGET_ACHIEVED: 0}
    unresolved = 0
    alive_examples = []

    for row in rows:
        verdict = evaluate(row, args.source)
        if verdict is None:
            unresolved += 1
            continue
        counts[verdict.validity] += 1
        marker = "ALIVE <-- thrown away while still intact" if verdict.alive else verdict.validity.value
        print(f"  {row['timestamp']}  {row['instrument']:7} {row['direction']:7} "
              f"entry={row['entry_price']} stop={row['stop_loss']} target={row['primary_target']}  "
              f"-> {marker}")
        if verdict.alive:
            alive_examples.append((row, verdict))

    total = sum(counts.values())
    print(f"\n{total} resolved ({unresolved} skipped -- no candle cache to check against)")
    if total:
        for validity, n in counts.items():
            print(f"  {validity.value:16} {n:4}  ({n / total:.0%})")
        print(f"\n{counts[Validity.ALIVE]} of {total} stale declines ({counts[Validity.ALIVE] / total:.0%}) "
              f"were still ALIVE by check_setup()'s price-based read -- "
              f"thrown away by the clock, not by the market.")


if __name__ == "__main__":
    main()
