import json
import logging
import urllib.error

import pytest

from .. import telegram_notify as tn


class FakeClock:
    """A controllable clock so rate-limiting tests don't depend on real
    wall-clock timing."""
    def __init__(self, start=0.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class RecordingHandler(tn.TelegramHandler):
    """Captures what _send() would have POSTed instead of making a real
    HTTP call, so tests never touch the network."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.sent: list[str] = []

    def _send(self, text):
        self.sent.append(text)


def make_record(msg, level=logging.WARNING):
    return logging.LogRecord(name="bot.orchestrator", level=level, pathname="", lineno=0,
                              msg=msg, args=(), exc_info=None)


def test_a_record_is_sent_immediately_when_nothing_was_sent_recently():
    clock = FakeClock()
    h = RecordingHandler("tok", "chat", clock=clock)
    h.emit(make_record("reconnect failed"))
    assert len(h.sent) == 1
    assert "reconnect failed" in h.sent[0]


def test_records_within_the_interval_are_batched_into_one_send():
    clock = FakeClock()
    h = RecordingHandler("tok", "chat", clock=clock)
    h.emit(make_record("first"))          # sends immediately
    clock.advance(1.0)                    # still inside MIN_SEND_INTERVAL
    h.emit(make_record("second"))
    clock.advance(1.0)
    h.emit(make_record("third"))

    assert len(h.sent) == 1                # only "first" has actually gone out
    assert h.sent[0] == "first"
    # second and third are queued, waiting for the interval to clear --
    # confirmed by flushing and checking they arrive together, not lost.
    h.flush()
    assert len(h.sent) == 2
    assert "second" in h.sent[1] and "third" in h.sent[1]


def test_a_record_after_the_interval_elapses_sends_its_own_batch():
    clock = FakeClock()
    h = RecordingHandler("tok", "chat", clock=clock)
    h.emit(make_record("first"))
    clock.advance(tn.TelegramHandler.MIN_SEND_INTERVAL + 0.1)
    h.emit(make_record("second"))

    assert len(h.sent) == 2
    assert "second" in h.sent[1]


def test_flush_sends_a_queued_batch_even_inside_the_interval():
    # The real reason flush() exists: a storm ends and nothing else
    # arrives to naturally trigger the next send -- run_live.py calls
    # this once per poll loop so a queued batch doesn't sit stranded.
    clock = FakeClock()
    h = RecordingHandler("tok", "chat", clock=clock)
    h.emit(make_record("first"))
    h.emit(make_record("queued"))  # inside the interval -- not sent yet
    assert len(h.sent) == 1

    h.flush()
    assert len(h.sent) == 2
    assert "queued" in h.sent[1]


def test_flush_with_nothing_pending_does_nothing():
    clock = FakeClock()
    h = RecordingHandler("tok", "chat", clock=clock)
    h.flush()
    assert h.sent == []


def test_records_below_the_configured_level_never_reach_emit(caplog):
    # Standard logging.Handler behavior (level filtering happens in
    # logging.Logger.callHandlers before emit() is ever invoked) --
    # asserted here because it's exactly what keeps this from forwarding
    # every DEBUG/INFO poll-loop line by default.
    clock = FakeClock()
    h = RecordingHandler("tok", "chat", level=logging.WARNING, clock=clock)
    logger = logging.getLogger("bot.telegram_notify_test_level")
    logger.addHandler(h)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    logger.info("routine poll-loop noise")
    logger.warning("something worth knowing")

    assert h.sent == ["something worth knowing"] or "something worth knowing" in h.sent[0]
    assert not any("routine" in s for s in h.sent)


def test_a_delivery_failure_does_not_raise(monkeypatch):
    # Must never take down the live bot or block a trading decision.
    h = tn.TelegramHandler("tok", "chat")

    def boom(req, timeout=None):
        raise urllib.error.URLError("network unreachable")

    monkeypatch.setattr(tn.urllib.request, "urlopen", boom)
    h.emit(make_record("this should not raise"))  # must not propagate the exception


def test_a_long_batch_is_truncated_not_silently_dropped():
    clock = FakeClock()
    h = RecordingHandler("tok", "chat", clock=clock)
    h.emit(make_record("x" * 10))
    for _ in range(500):
        clock.t += 0.001  # stay inside the interval -- keep queuing
        h.emit(make_record("y" * 20))
    h.flush()

    assert len(h.sent) == 2
    assert len(h.sent[1]) <= tn.MAX_MESSAGE_CHARS + 100
    assert "truncated" in h.sent[1]


def test_the_actual_http_request_is_shaped_correctly(monkeypatch):
    captured = {}

    class FakeResponse:
        def read(self):
            return b"ok"

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(tn.urllib.request, "urlopen", fake_urlopen)
    h = tn.TelegramHandler("mytoken", "12345")
    h.emit(make_record("hello"))

    assert captured["url"] == "https://api.telegram.org/botmytoken/sendMessage"
    assert captured["body"] == {"chat_id": "12345", "text": "hello"}


def test_attach_if_configured_is_a_no_op_without_both_env_vars(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert tn.attach_if_configured() is None

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert tn.attach_if_configured() is None


def test_attach_if_configured_wires_a_handler_onto_the_bot_logger(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    bot_logger = logging.getLogger("bot")
    before = list(bot_logger.handlers)
    try:
        handler = tn.attach_if_configured()
        assert handler is not None
        assert handler in bot_logger.handlers
    finally:
        for h in bot_logger.handlers[:]:
            if h not in before:
                bot_logger.removeHandler(h)


def test_the_internal_failure_logger_does_not_feed_back_into_bot():
    # If this were ever True, a sustained Telegram outage would have the
    # handler try to report its own delivery failure to itself, forever.
    assert tn._internal_logger.propagate is False
