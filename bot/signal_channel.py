"""
The second Telegram channel: bias, storyline and confirmations only.

Operator, 2026-09-25: "I want to focus on the bias and storylines and
confirmation notifications while I validate it and take the trade if it
looks good to me."

So this is not the log stream. `telegram_notify.py` stays exactly as it
is and keeps receiving everything -- warnings, reconnects, execution
events -- on the old bot, which is muted. This channel carries four
kinds of message and nothing else:

    bias      an instrument's storyline stage changed
    aligned   it reached HUNTING: the timeframes agree, drop to H1
    setup     liquidity taken and a key level played
    entry     a confirmation appeared, with its numbers

WHY THE REASONING GOES IN THE MESSAGE

"It should be adding the thought process in the message." A line saying
"EURUSD hunting bullish" cannot be checked. A message that says WHICH
timeframes agree, WHEN each of them last confirmed, which one carries
the bias, and what is being waited for can be held against the chart in
thirty seconds -- which is the entire point of a human in the loop. Every
field here already existed; the bot was logging it to a file nobody
reads.

NO TRADING DECISIONS ARE MADE HERE

This module formats and sends. It never decides, never sizes, never
places. A failure to reach Telegram is swallowed, because a notifier
that can take down a trading process is worse than no notifier -- the
same rule telegram_notify.py has followed since it was written.

CREDENTIALS

SLK_SIGNAL_TOKEN and SLK_SIGNAL_CHAT from the environment, never a
committed file. Deliberately NOT the same variable names as the log
channel, so the two cannot be crossed by accident, and so one can be
rotated without touching the other. If either is unset,
`from_env()` returns None and every call becomes a no-op -- a bot with
no signal channel configured behaves exactly as it did before this
existed.
"""

from __future__ import annotations

import logging
import os

from .telegram_notify import send_message

logger = logging.getLogger("bot.signal_channel")
logger.propagate = False        # never feed our own failures back into "bot"

TOKEN_VAR = "SLK_SIGNAL_TOKEN"
CHAT_VAR = "SLK_SIGNAL_CHAT"


def _fmt_time(value) -> str:
    """A timestamp a person can compare against a chart at a glance."""
    if value is None:
        return "--"
    text = str(value)
    return text[:16] if len(text) > 16 else text


def _pips(instrument: str, distance: float) -> str:
    from backtest.engine.runner import default_pip_size
    pip = default_pip_size(instrument)
    return f"{distance / pip:.1f} pips" if pip else f"{distance:g}"


class SignalChannel:
    """Formats and sends. Holds no state beyond its credentials."""

    def __init__(self, token: str, chat_id: str, label: str = ""):
        self.token = token
        self.chat_id = chat_id
        self.label = label          # which engine spoke, when two are running

    @classmethod
    def from_env(cls, label: str = "") -> "SignalChannel | None":
        token = os.environ.get(TOKEN_VAR, "").strip()
        chat = os.environ.get(CHAT_VAR, "").strip()
        if not token or not chat:
            return None
        return cls(token, chat, label)

    def _send(self, text: str) -> bool:
        if self.label:
            text = f"[{self.label}] {text}"
        try:
            return send_message(self.token, self.chat_id, text)
        except Exception as exc:                       # noqa: BLE001
            # Never propagate. See the module note.
            logger.warning("signal channel send failed: %s", exc)
            return False

    # --- the four message kinds ---------------------------------------

    def storyline(self, instrument: str, storyline, previous: str | None) -> bool:
        """An instrument's stage changed. The whole reason, not a verdict.

        Sent on the TRANSITION only. The stage is rechecked every cycle
        and would otherwise repeat every few seconds for days.
        """
        hunting = getattr(storyline, "direction", None) is not None
        head = "ALIGNED" if hunting else "waiting"
        mark = "🟢" if hunting else "⚪"
        direction = getattr(storyline, "direction", None)
        arrow = f" {direction.value}" if direction is not None else ""

        lines = [f"{mark} {instrument} — {head}{arrow}", ""]
        lines.append(getattr(storyline, "reason", ""))
        lines.append("")

        for name, attr in (("Weekly", "weekly_confirmed_at"),
                           ("Daily", "daily_confirmed_at"),
                           ("H4", "h4_confirmed_at")):
            when = getattr(storyline, attr, None)
            if when is not None:
                lines.append(f"  {name:<7} confirmed {_fmt_time(when)}")

        effective = getattr(storyline, "effective_tf", None)
        if effective:
            lines.append(f"  bias carried by {effective}")
        if previous:
            lines.append(f"  (was: {previous})")

        if hunting:
            lines += [
                "",
                "Now watching H1 for:",
                "  liquidity taken, the nearest key level to it played,",
                "  then your confirmation — engulf, sweep+break,",
                "  breakout or the 4th-man V-shape.",
            ]
        return self._send("\n".join(lines))

    def setup(self, instrument: str, direction, level_price: float,
              liquidity_price: float, timeframe: str = "H4") -> bool:
        """Liquidity taken and the key level played -- the SLK setup, before
        any confirmation exists. This is the "go and look" message."""
        side = getattr(direction, "value", direction)
        lines = [
            f"🟡 {instrument} — SETUP {side}",
            "",
            f"  {timeframe} liquidity taken at {liquidity_price:g}",
            f"  key level played   {level_price:g}",
            "",
            "Waiting on a confirmation entry. Nothing to do yet.",
        ]
        return self._send("\n".join(lines))

    def confirmation(self, instrument: str, direction, form: str,
                     entry: float, stop: float, target: float | None,
                     storyline_reason: str = "",
                     level_price: float | None = None,
                     liquidity_price: float | None = None) -> bool:
        """A confirmation appeared. Everything needed to judge it."""
        side = getattr(direction, "value", direction)
        risk = abs(entry - stop)
        lines = [f"🔵 {instrument} — {form.upper()} {side}", ""]
        lines.append(f"  entry   {entry:g}")
        lines.append(f"  stop    {stop:g}   ({_pips(instrument, risk)})")
        if target is not None:
            reward = abs(target - entry)
            rr = (reward / risk) if risk else 0.0
            lines.append(f"  target  {target:g}   ({rr:.1f}R)")
        else:
            lines.append("  target  none standing — no external liquidity above/below")

        if level_price is not None:
            lines.append(f"  key level {level_price:g}")
        if liquidity_price is not None:
            lines.append(f"  liquidity taken {liquidity_price:g}")
        if storyline_reason:
            lines += ["", storyline_reason]

        lines += ["", "Your call — check it before you take it."]
        return self._send("\n".join(lines))

    def note(self, text: str) -> bool:
        """Anything that is not one of the four, kept rare on purpose."""
        return self._send(text)
