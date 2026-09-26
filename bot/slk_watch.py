"""
The SLK side, watching and reporting. It never trades.

Operator, 2026-09-25: "for the SLK own, remember SLK is using single
candle liquidity ... it's going to tell you, for example, daily reject
from this key level, four hours breakout, or weekly sweep -- low swept,
high is still standing, that is building the bias with liquidity."

So this is the second engine, running beside the old bot rather than
replacing it -- "my old system, don't change it ... I want to be using
two of them as confluence." Two engines, two stories, both labelled,
never merged.

HOW IT AVOIDS BEING A SECOND MACHINE

It does not reimplement the cascade. It calls `backtest.slk.replay`, the
same function the backtest calls, and listens through its observer hook.
Anything the backtest would have traded is exactly what gets reported,
because it is the same code reaching the same decision. A separate live
implementation would eventually disagree with the backtest, and this
project has paid for that twice.

WHY IT RECOMPUTES INSTEAD OF HOLDING STATE

Each cycle replays the instrument's trimmed history from scratch and
reports only what is newer than the watermark. That is more work than
keeping the streams alive between candles, and it buys two things worth
more than the cycles: a restart loses nothing, and there is no
long-lived state to drift out of step with the market. The old bot
rebuilds its higher-timeframe context the same way and for the same
reason.

The trimmed windows are the ones in bot/history_windows.json -- the only
history the live side ever sees, so the thing being reported is the
thing that was measured.

NOTHING HERE PLACES AN ORDER

There is no execution client in this module and no import that could
reach one. That is the design, not an omission: the operator asked for
notifications while they judge the trades themselves.
"""

from __future__ import annotations

import logging

from backtest.slk import narrative
from backtest.slk.replay import replay

logger = logging.getLogger("bot.slk_watch")

# Rung names, so a sentence can say which timeframe did what. The cascade
# runs both routes on both rungs; these are the pairs it runs them on.
UPPER = ("Weekly", "Daily")
LOWER = ("Daily", "H4")


class _Collector:
    """Receives the replay's events and keeps the ones past the watermark.

    Deliberately dumb: it stores, it does not decide. Deciding what is
    worth sending happens once, in `SLKWatcher`, where the whole cycle's
    events are visible -- a bias change and the setup it enabled in the
    same hour should read as one story, not two pings.
    """

    def __init__(self, since):
        self.since = since
        self.bias = []
        self.setups = []
        self.confirmations = []
        # The LAST bias seen, regardless of the watermark. The watermark
        # decides what is news; this is what is TRUE right now, and on
        # the first cycle -- when nothing is news because everything is
        # history -- it is the only thing worth saying.
        self.standing = None

    def _fresh(self, at) -> bool:
        return self.since is None or (at is not None and at > self.since)

    def on_bias(self, at=None, direction=None, cascade=None, was=None):
        # The ACCOUNT, not a direction: which rung leads, by which route,
        # what the other rung says and why it is not leading. The summary
        # this replaced read the Daily route every time and so reported
        # "key level rejected" for all 27 instruments regardless of what
        # had actually carried the bias.
        account = _account(cascade)
        if direction is not None:
            self.standing = {"at": at, "account": account}
        if self._fresh(at) and direction is not None:
            self.bias.append({"at": at, "was": was, "account": account})

    def on_setup(self, at=None, setup=None, direction=None, target=None):
        if self._fresh(at):
            self.setups.append({"at": at, "setup": setup,
                                 "direction": direction, "target": target})

    def on_confirmation(self, at=None, form=None, direction=None, entry=None,
                        stop=None, target=None, setup=None):
        if self._fresh(at):
            self.confirmations.append({"at": at, "form": form,
                                        "direction": direction, "entry": entry,
                                        "stop": stop, "target": target,
                                        "setup": setup})


def _account(cascade):
    """The cascade's own account of the bias, or None.

    Never raises: a missing description must cost the detail, never the
    message.
    """
    if cascade is None:
        return None
    try:
        return cascade.explain()
    except Exception:                                   # noqa: BLE001
        logger.exception("could not read the bias account")
        return None


class SLKWatcher:
    """One instrument, watched. Call `check` when an H1 candle closes."""

    def __init__(self, instrument: str, n: int, channel, load_candles,
                 newest_time=None):
        self.instrument = instrument
        self.n = n
        self.channel = channel
        self.load = load_candles           # (instrument, granularity) -> list
        self.watermark = None              # nothing before this is news
        self.standing = None               # the bias as it stands, if any
        # A cheap "has anything closed since I last looked". Optional so
        # tests and one-off runs need not provide one.
        self.newest_time = newest_time

    def _series(self):
        out = {}
        for code in ("W", "D", "H4", "H1"):
            out[code] = self.load(self.instrument, code)
        return out

    def check(self) -> int:
        """Replay, report what is new, advance the watermark.

        Returns how many messages were sent, which is only used for
        logging -- a cycle that sends nothing is the normal case and must
        stay silent.
        """
        # Skip the replay entirely when no H1 candle has closed since
        # the last look.
        #
        # Without this every cycle replayed all 27 instruments whether or
        # not anything had happened -- about six minutes of work, running
        # continuously, for an answer that changes once an hour. Worse,
        # it meant a confirmation could sit behind twenty-six other
        # instruments' pointless replays before anyone heard about it.
        # Operator: "hope the SLK bias bot will respond fast even to
        # confirmation entry once they present themselves, not hours
        # later."
        if self.watermark is not None and self.newest_time is not None:
            latest = self.newest_time(self.instrument, "H1")
            if latest is not None and str(latest) <= str(self.watermark):
                return 0

        series = self._series()
        if not series["H1"]:
            return 0

        collector = _Collector(self.watermark)
        replay(series["W"], series["D"], series["H4"], series["H1"],
               self.n, observer=collector)

        sent = 0
        self.standing = collector.standing
        if self.watermark is None:
            # First pass: the whole history is "new". Reporting it would
            # be years of messages, so the first cycle only learns where
            # now is -- and records the bias as it stands, which the
            # runner announces once as a single summary.
            logger.info("%s: bootstrapped, watching from %s",
                         self.instrument, series["H1"][-1].time)
        else:
            sent = self._report(collector)

        self.watermark = series["H1"][-1].time
        return sent

    def _report(self, collector) -> int:
        """Send what is new.

        Every send is guarded HERE as well as inside the channel. The
        channel swallows its own transport failures, but the channel is
        an argument -- anything can be passed in, and a watcher that
        stops watching because a notifier raised is worse than one that
        misses a message. A test passes a channel that always raises.
        """
        sent = 0
        for send, items in ((self._send_bias, collector.bias),
                            (self._send_setup, collector.setups),
                            (self._send_confirmation, collector.confirmations)):
            for item in items:
                try:
                    if send(item):
                        sent += 1
                except Exception:                      # noqa: BLE001
                    logger.exception("%s: could not send a %s message",
                                      self.instrument, send.__name__)
        return sent

    def standing_story(self) -> str:
        """The whole current bias for this instrument, as its own message.

        One message PER INSTRUMENT, not a batch. Operator, 2026-09-25:
        "it shouldn't even be coming as a badge ... it should be coming
        individual ... it's not even saying what the daily did, it's not
        saying what the weekly did." A list of 27 one-liners cannot say
        any of that, and a summary that has to fit on one line will
        always end up naming the wrong cause.
        """
        if not self.standing or not self.standing.get("account"):
            return ""
        return "🟢 [SLK] " + "\n".join(
            narrative.account_story(self.standing["account"], self.instrument))

    def _send_bias(self, change) -> bool:
        account = change.get("account")
        if account is None or account.direction is None:
            logger.info("%s: bias changed with no account to describe -- "
                         "not sent", self.instrument)
            return False
        lines = ["🟢 [SLK] BIAS CHANGE"]
        if change.get("was") is not None:
            lines.append(f"(was {getattr(change['was'], 'value', '')})")
        lines.append("")
        lines += narrative.account_story(account, self.instrument)
        return bool(self.channel.note("\n".join(lines)))

    def _send_setup(self, item) -> bool:
        setup = item["setup"]
        level = getattr(getattr(setup, "level", None), "price", None)
        liquidity = getattr(getattr(getattr(setup, "sweep", None), "point", None),
                            "price", None)
        if level is None or liquidity is None:
            return False

        lines = [f"🟡 {self.instrument} — SLK SETUP "
                 f"{getattr(item['direction'], 'value', '')}", ""]
        lines += narrative.liquidity_taken_sentence(
            self.instrument, item["direction"], liquidity, level)
        if item.get("target"):
            lines.append(f"External liquidity to aim at: {item['target']:g}.")
        return bool(self.channel.note("\n".join(lines)))

    def _send_confirmation(self, item) -> bool:
        setup = item["setup"]
        level = getattr(getattr(setup, "level", None), "price", None)
        liquidity = getattr(getattr(getattr(setup, "sweep", None), "point", None),
                            "price", None)
        side = getattr(item["direction"], "value", item["direction"])
        lines = [f"🔵 {self.instrument} — SLK CONFIRMATION {side}", ""]
        lines += narrative.confirmation_story(
            item["form"], item["entry"], item["stop"], item["target"])
        if level is not None:
            lines.append(f"  key level played: {level:g}")
        if liquidity is not None:
            lines.append(f"  liquidity that entitled it: {liquidity:g}")
        lines += ["", "Your call — check it before you take it."]
        return bool(self.channel.note("\n".join(lines)))
