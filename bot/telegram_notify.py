"""
Pushes the live bot's important events to a Telegram chat -- so "is
anything happening" doesn't require SSHing into the VPS and tailing
tmux panes or SQLite files by hand.

Attaches as a standard logging.Handler on the "bot" logger, which every
module in this package logs under (bot.orchestrator, bot.run_live,
bot.mt5_data, ...) and which propagates child records up automatically.
That means this file doesn't need to know what those modules log or
when they log it -- it just receives whatever they already send through
logger.info/warning/error/exception. The one gap that mattered: trade
EXITS used to only ever reach audit_log.update_outcome() (SQLite),
never the standard logger at all, so a win or loss would never have
shown up here no matter what this handler did. orchestrator.py's
_record_closed_trade() now also logs a line -- see that function.

Deliberately NOT the whole log stream. Sending every DEBUG/INFO
poll-loop line (25 instruments x 2 bots, checked every 5 seconds) would
be useless on a phone and would risk tripping Telegram's own per-chat
rate limit. The default level is WARNING; orchestrator.py's own INFO
lines for entries/exits/phase transitions are explicit enough to opt
into as well (attach_if_configured's caller decides the level).

Rate limiting, separate from the level filter: a real reconnect storm
(bot/OPERATIONS_LOG.md, 2026-08-27/28) produced 150+ WARNING lines
before backoff existed, and even with backoff a burst of several in a
few seconds is plausible. Records arriving within MIN_SEND_INTERVAL of
the last actual send are queued and combined into one message rather
than each firing its own HTTP call -- see TelegramHandler's docstring.

Credentials come from environment variables only, matching every other
secret in this project (see config.py's module docstring) -- never a
committed file. TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID; if either is
unset, attach_if_configured() is a no-op and the bot behaves exactly as
it did before this existed.

A failure to reach Telegram must NEVER take down the live bot or block
a trading decision. Every send is best-effort and wrapped; a failure is
logged locally through a logger that does NOT propagate back into "bot"
(propagate=False below) -- without that, a sustained Telegram outage
would have this handler try to report its own failure to itself,
forever.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_CHARS = 3500  # Telegram's real cap is 4096; leave headroom for the truncation note

_internal_logger = logging.getLogger("bot.telegram_notify")
_internal_logger.propagate = False  # see module docstring -- must not feed back into its own handler


class TelegramHandler(logging.Handler):
    """logging.Handler that pushes formatted records to a Telegram chat,
    rate-limited to at most one HTTP request per MIN_SEND_INTERVAL.

    A record arriving less than MIN_SEND_INTERVAL after the last actual
    send is queued rather than sent immediately; the NEXT record whose
    arrival clears that interval flushes the whole queue as one message.
    Call flush() periodically (run_live.py does this once per poll loop)
    to guarantee a queued batch still goes out promptly even if nothing
    else triggers it -- e.g. right after a storm ends and no further
    records arrive to naturally trigger the next send.

    Confirmed live 2026-08-30: Telegram's OWN flood control (HTTP 429)
    blocked this bot's messages for 1h45m+ after an earlier spam
    incident (see bot/OPERATIONS_LOG.md), across every single WARNING
    and INFO event that whole time -- real trading decisions, not just
    noise, silently never reaching the chat. The 429 response's body
    carries a `retry_after` seconds value; this handler used to ignore
    it completely and just retry on the very next event, getting another
    429 every time. Retrying INSIDE an active flood-control window is
    exactly what keeps renewing it, which is almost certainly why a
    normal transient block ran for that long instead of clearing on its
    own. `_blocked_until` now makes both emit() and flush() skip
    attempting a send entirely until Telegram's own stated cooldown (or
    a default/doubling fallback if it didn't say) has actually passed --
    still queuing so nothing is lost, just not hammering a block."""

    MIN_SEND_INTERVAL = 3.0
    DEFAULT_BACKOFF_SECONDS = 60.0
    MAX_BACKOFF_SECONDS = 1800.0  # 30 min cap -- a malformed response must not wedge delivery forever

    def __init__(self, token: str, chat_id: str, level=logging.WARNING, clock=time.monotonic):
        super().__init__(level=level)
        self._token = token
        self._chat_id = chat_id
        self._clock = clock
        self._pending: list[str] = []
        self._last_sent_at: float | None = None
        self._blocked_until: float | None = None
        self._backoff_seconds = self.DEFAULT_BACKOFF_SECONDS

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
        except Exception:
            return  # formatting itself failing must not cascade or crash the bot
        self._pending.append(text)
        now = self._clock()
        if self._blocked_until is not None and now < self._blocked_until:
            return  # still inside Telegram's own flood-control window -- stay queued, don't retry yet
        if self._last_sent_at is not None and now - self._last_sent_at < self.MIN_SEND_INTERVAL:
            return  # queued -- goes out with whichever record next clears the interval
        self._do_flush(now)

    def flush(self) -> None:
        """Send whatever is queued right now, bypassing the interval --
        for "make sure nothing is left stranded," not normal operation.
        Still respects an active flood-control block: called once per
        poll loop by run_live.py, so without this check it would retry
        into a live block every few seconds, same as emit() would."""
        now = self._clock()
        if self._pending and (self._blocked_until is None or now >= self._blocked_until):
            self._do_flush(now)

    def _do_flush(self, now: float) -> None:
        batch, self._pending = self._pending, []
        text = "\n\n".join(batch)
        if len(text) > MAX_MESSAGE_CHARS:
            text = text[:MAX_MESSAGE_CHARS] + f"\n... ({len(batch)} events, truncated)"
        self._last_sent_at = now
        self._send(text)

    def _send(self, text: str) -> None:
        payload = json.dumps({"chat_id": self._chat_id, "text": text}).encode()
        req = urllib.request.Request(
            TELEGRAM_API.format(token=self._token), data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=10).read()
            self._blocked_until = None
            self._backoff_seconds = self.DEFAULT_BACKOFF_SECONDS
        except urllib.error.HTTPError as exc:
            retry_after = self._retry_after_seconds(exc)
            wait = retry_after if retry_after is not None else self._backoff_seconds
            self._blocked_until = self._clock() + wait
            self._backoff_seconds = min(self._backoff_seconds * 2, self.MAX_BACKOFF_SECONDS)
            _internal_logger.warning(
                "failed to deliver Telegram notification: %s -- backing off %.0fs before retrying",
                exc, wait)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            _internal_logger.warning("failed to deliver Telegram notification: %s", exc)

    @staticmethod
    def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
        """Telegram's 429 body is {"parameters": {"retry_after": N}, ...}
        per the Bot API spec. None if the body doesn't have it (a
        different HTTP error, or a malformed/unexpected response) --
        callers fall back to the default/doubling backoff in that case."""
        try:
            body = json.loads(exc.read())
            return float(body["parameters"]["retry_after"])
        except Exception:
            return None

    def close(self) -> None:
        self.flush()
        super().close()


def attach_if_configured(level=logging.WARNING) -> TelegramHandler | None:
    """Wires a TelegramHandler onto the "bot" logger if TELEGRAM_BOT_TOKEN
    and TELEGRAM_CHAT_ID are both set in the environment; otherwise a
    no-op, so this whole feature is entirely opt-in and absent by
    default. Returns the handler (so the caller can flush() it
    periodically) or None."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return None
    handler = TelegramHandler(token, chat_id, level=level)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger("bot").addHandler(handler)
    return handler
