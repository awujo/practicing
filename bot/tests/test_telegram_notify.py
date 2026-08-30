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


def _http_429(retry_after=None):
    body = {"ok": False, "error_code": 429, "description": "Too Many Requests"}
    if retry_after is not None:
        body["parameters"] = {"retry_after": retry_after}
    import io
    return urllib.error.HTTPError(
        "https://api.telegram.org/x", 429, "Too Many Requests", {},
        io.BytesIO(json.dumps(body).encode()))


def test_a_429_with_retry_after_blocks_further_sends_until_it_elapses(monkeypatch):
    # Confirmed live 2026-08-30: without this, every subsequent event
    # retried immediately, got another 429, and (per Telegram's own
    # flood-control behavior) kept renewing the block -- 1h45m+ of real
    # trading decisions never reaching the chat.
    clock = FakeClock()
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(1)
        raise _http_429(retry_after=30)

    monkeypatch.setattr(tn.urllib.request, "urlopen", fake_urlopen)
    h = tn.TelegramHandler("tok", "chat", clock=clock)

    h.emit(make_record("first"))          # attempts, gets 429, blocked_until = 30
    assert len(calls) == 1

    clock.advance(tn.TelegramHandler.MIN_SEND_INTERVAL + 1)
    h.emit(make_record("second"))         # still well inside the 30s block -- must NOT retry
    assert len(calls) == 1

    clock.advance(29)                     # now at t=~33, past the 30s block
    h.emit(make_record("third"))
    assert len(calls) == 2                # retried only once the block actually elapsed


def test_flush_also_respects_an_active_block(monkeypatch):
    # run_live.py calls flush() once per poll loop (every few seconds) --
    # without this, THAT alone would hammer an active block just as badly
    # as emit() retrying on every new event. A failed send's own batch is
    # dropped (pre-existing best-effort behavior -- module docstring: "a
    # failure to reach Telegram must never... block a trading decision"),
    # so this checks that a NEW event queued during the block stays
    # queued rather than being attempted, and only goes out once the
    # block actually clears.
    clock = FakeClock()
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(1)
        raise _http_429(retry_after=30)

    monkeypatch.setattr(tn.urllib.request, "urlopen", fake_urlopen)
    h = tn.TelegramHandler("tok", "chat", clock=clock)
    h.emit(make_record("first"))  # attempts, fails, now blocked for 30s
    assert len(calls) == 1

    h.emit(make_record("second"))  # queued only -- still blocked, must not attempt
    assert len(calls) == 1
    h.flush()  # still blocked -- must not attempt either
    h.flush()
    assert len(calls) == 1

    clock.advance(31)
    h.flush()  # block cleared -- "second" finally goes out
    assert len(calls) == 2


def test_a_429_without_retry_after_falls_back_to_a_default_backoff(monkeypatch):
    clock = FakeClock()
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(1)
        raise _http_429(retry_after=None)

    monkeypatch.setattr(tn.urllib.request, "urlopen", fake_urlopen)
    h = tn.TelegramHandler("tok", "chat", clock=clock)
    h.emit(make_record("first"))
    assert len(calls) == 1

    clock.advance(tn.TelegramHandler.DEFAULT_BACKOFF_SECONDS - 1)
    h.emit(make_record("too soon"))
    assert len(calls) == 1

    clock.advance(2)
    h.emit(make_record("now"))
    assert len(calls) == 2


def test_a_successful_send_after_a_block_clears_it_and_resets_the_backoff(monkeypatch):
    clock = FakeClock()
    state = {"fail": True}

    def fake_urlopen(req, timeout=None):
        if state["fail"]:
            raise _http_429(retry_after=10)

        class R:
            def read(self):
                return b"ok"
        return R()

    monkeypatch.setattr(tn.urllib.request, "urlopen", fake_urlopen)
    h = tn.TelegramHandler("tok", "chat", clock=clock)
    h.emit(make_record("first"))  # blocked for 10s
    assert h._blocked_until is not None

    clock.advance(11)
    state["fail"] = False
    h.emit(make_record("recovers"))
    assert h._blocked_until is None
    assert h._backoff_seconds == tn.TelegramHandler.DEFAULT_BACKOFF_SECONDS


def test_repeated_429s_without_retry_after_double_the_backoff_up_to_a_cap(monkeypatch):
    clock = FakeClock()

    def fake_urlopen(req, timeout=None):
        raise _http_429(retry_after=None)

    monkeypatch.setattr(tn.urllib.request, "urlopen", fake_urlopen)
    h = tn.TelegramHandler("tok", "chat", clock=clock)

    h.emit(make_record("1"))
    assert h._backoff_seconds == tn.TelegramHandler.DEFAULT_BACKOFF_SECONDS * 2

    clock.advance(tn.TelegramHandler.DEFAULT_BACKOFF_SECONDS + 1)
    h.emit(make_record("2"))
    assert h._backoff_seconds == tn.TelegramHandler.DEFAULT_BACKOFF_SECONDS * 4
