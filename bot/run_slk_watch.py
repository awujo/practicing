"""
The SLK watcher as a process. It reports; it never trades.

    docker exec -d -u abc -w /config/trading mt5 sh -c \\
        'python3 -u -m bot.run_slk_watch --n 2 \\
            --instruments EURUSD,GBPJPY,AUDCAD \\
            --history-windows-config bot/history_windows.json \\
            > /config/slk_watch.log 2>&1'

It runs beside the old bot rather than replacing it. Operator,
2026-09-25: "my old system, don't change it ... I want to be using two
of them as confluence." Two engines, two stories, both labelled in
Telegram, never merged.

WHAT IT SENDS, AND WHERE

To the signal channel only (SLK_SIGNAL_TOKEN / SLK_SIGNAL_CHAT), the
same second Telegram bot the old bot's bias notifications use, tagged
[SLK] so the two can never be confused:

    BIAS          a rung changed, with the story that made it --
                  which timeframe swept what, or rejected which level,
                  and which timeframe then broke structure to confirm
    SETUP         single candle liquidity taken, and the nearest key
                  level to it being played
    CONFIRMATION  an entry appeared, with its numbers

Nothing else. Operational noise -- reconnects, MT5 up and down, cycle
timings -- stays on the old channel, which is the one being muted.

CANDLES COME FROM THE CACHE, NOT FROM MT5 DIRECTLY

The same CSV cache the old bot and every backtest read, kept current by
the live sync that already runs. That means this process needs no broker
connection at all, which is why it cannot place an order even by
accident, and why it can run while MT5 is down.

TRIMMED HISTORY, ON PURPOSE

--history-windows-config takes the same bot/history_windows.json the old
bot uses: one or two years per instrument rather than twenty. That is
the only history the live side ever sees, so what is reported is what
was measured -- and it keeps a cycle to seconds rather than minutes.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

from backtest.data_pipeline.instruments import DUKASCOPY_INSTRUMENTS
from backtest.engine.candles import load_candles

from .signal_channel import SignalChannel
from .slk_watch import SLKWatcher

logger = logging.getLogger("bot.run_slk_watch")

POLL_SECONDS = 60


def _trim(candles, years: float | None):
    """Keep the last `years` of a series. None keeps everything."""
    if not years or not candles:
        return candles
    import pandas as pd
    cutoff = candles[-1].time - pd.Timedelta(days=365.25 * years)
    return [c for c in candles if c.time >= cutoff]


def _loader(source: str, windows: "_Windows"):
    """(instrument, granularity) -> candles, trimmed to the live window.

    A load failure returns an empty series rather than raising: one
    instrument's missing cache file must not stop the other 24 being
    watched.
    """
    def load(instrument: str, granularity: str):
        try:
            candles = load_candles(source, instrument, granularity)
        except Exception as exc:                        # noqa: BLE001
            logger.warning("%s %s: cannot load -- %s",
                            instrument, granularity, exc)
            return []
        return _trim(candles, windows.for_instrument(instrument).get(granularity))
    return load


class _Windows:
    """The trimmed history each instrument gets, from the file the old bot
    reads.

    Three cases, and the middle one is why this is a class rather than a
    dict lookup:

      listed with a window   use it
      listed as NULL         full history. An explicit null means
                             "confirmed NOT safe to cap" (GBPNZD), and
                             falling back to the default there would cut
                             the one instrument that must not be cut.
      NOT LISTED AT ALL      the file's default. USOIL and ETHUSD are in
                             instruments.py but were never in the live
                             list, so they are not in this file either --
                             and without the fallback each would quietly
                             pull twenty years and make a cycle crawl.
    """

    def __init__(self, default: dict, per_instrument: dict):
        self.default = default
        self.per_instrument = per_instrument

    def for_instrument(self, instrument: str) -> dict:
        if instrument in self.per_instrument:
            return self.per_instrument[instrument]
        return self.default


def _windows(path: str | None) -> _Windows:
    if not path:
        return _Windows({}, {})
    with open(path) as handle:
        raw = json.load(handle)
    per_instrument = {}
    for instrument, window in (raw.get("instruments") or {}).items():
        per_instrument[instrument] = {} if window is None else window
    return _Windows(raw.get("default", {}), per_instrument)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instruments", required=True,
                        help="comma separated, e.g. EURUSD,GBPJPY -- or ALL "
                             "for every instrument in instruments.py, which "
                             "is the 25 the old bots watch plus USOIL and "
                             "ETHUSD.")
    parser.add_argument("--n", type=int, required=True,
                        help="swing width. REQUIRED -- the course gives no "
                             "number, so the caller has to choose one and say "
                             "which. See backtest/slk/stream.py.")
    parser.add_argument("--source", default="dukascopy")
    parser.add_argument("--history-windows-config", default=None,
                        help="bot/history_windows.json -- the same trimmed "
                             "windows the live bot loads.")
    parser.add_argument("--poll-seconds", type=int, default=POLL_SECONDS)
    parser.add_argument("--once", action="store_true",
                        help="one cycle and exit, for checking the wiring.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    channel = SignalChannel.from_env(label="SLK")
    if channel is None:
        sys.exit("No signal channel configured. Set SLK_SIGNAL_TOKEN and "
                 "SLK_SIGNAL_CHAT -- without them this process would watch "
                 "and tell nobody.")

    if args.instruments.strip().upper() == "ALL":
        instruments = sorted(DUKASCOPY_INSTRUMENTS)
    else:
        instruments = [s.strip().upper() for s in args.instruments.split(",")
                       if s.strip()]
    windows = _windows(args.history_windows_config)
    load = _loader(args.source, windows)

    watchers = [SLKWatcher(instrument, args.n, channel, load)
                for instrument in instruments]
    logger.info("SLK watcher starting on %d instruments, n=%d "
                 "(reporting only -- nothing is traded)",
                 len(watchers), args.n)

    first = True
    while True:
        started = time.time()
        total = 0
        for watcher in watchers:
            try:
                total += watcher.check()
            except Exception:                           # noqa: BLE001
                # One instrument's failure must never stop the rest.
                logger.exception("%s: cycle failed", watcher.instrument)

        if first:
            # The first cycle is silent by design -- everything in the
            # trimmed history is already in the past. But a watcher that
            # starts up and says nothing for hours is indistinguishable
            # from one that is broken, so it announces what it can
            # already see, once. It doubles as the state of the book:
            # where every pair currently stands before anything moves.
            _announce(channel, watchers, args.n)
            first = False

        logger.info("cycle done in %.0fs, %d message(s) sent",
                     time.time() - started, total)
        if args.once:
            return
        time.sleep(max(5, args.poll_seconds))


def _announce(channel, watchers, n: int) -> None:
    """One message at startup: what is being watched and where it stands."""
    with_bias = [w for w in watchers if w.standing]
    lines = [f"[SLK] watching {len(watchers)} instruments, n={n}",
             "Reporting only — nothing is traded.", ""]
    if with_bias:
        lines.append(f"Bias standing right now ({len(with_bias)}):")
        lines += [w.summary_line() for w in with_bias]
    else:
        lines.append("No bias standing on any pair right now.")
    quiet = len(watchers) - len(with_bias)
    if quiet:
        lines.append(f"")
        lines.append(f"The other {quiet} have no bias yet.")
    lines += ["", "From here you will hear about changes only:",
              "a bias forming, liquidity being taken, a confirmation."]
    try:
        channel.note("\n".join(lines))
    except Exception:                                   # noqa: BLE001
        logger.exception("could not send the startup announcement")


if __name__ == "__main__":
    main()
