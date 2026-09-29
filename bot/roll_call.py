"""
The roll call: every instrument, grouped by what it is worth today.

Operator, 2026-09-26: "at the beginning of every new day it runs the new
daily analysis for all the pairs and logs it to telegram ... so that at
the beginning of a new day, when the market has reset, I can just look
at the new report, know the pairs to put in my watch list, know the ones
to remove, know the ones I'll be focusing on that day."

So this is not a notification. It is a WATCHLIST, and it is built to be
read once in the morning and acted on:

    ALIGNED        Weekly and Daily agree. The day's focus.
    NOT ALIGNED    they disagree -- tradeable, lower probability, and
                   Bishop takes a nearer target when he takes it
    ONE TIMEFRAME  only one has broken structure, so there is nothing
                   to align with yet
    NO BIAS        neither has. Nothing to watch.

ONE MESSAGE, NOT TWENTY-SEVEN

A roll call that arrives as 27 pings is a roll call nobody reads. The
detail per instrument already arrives as it happens; this is the shape
of the whole book at a glance.

WHY IT ALSO FIRES ON RESTART

Same information, same need: "that kind of thing that happens if we
restart". A process that has just come up and a market that has just
rolled over are the same situation from the reader's side -- neither of
them has told you anything yet today.
"""

from __future__ import annotations

ALIGNED = "aligned"
NOT_ALIGNED = "not aligned"
DAILY_ONLY = "daily only"
WEEKLY_ONLY = "weekly only"

# Order matters: the day's focus first, the noise last.
GROUPS = (
    (ALIGNED, "ALIGNED — Weekly and Daily agree. Today's focus."),
    (NOT_ALIGNED, "NOT ALIGNED — lower probability; may be a retracement "
                  "inside the Weekly."),
    (DAILY_ONLY, "DAILY ONLY — no Weekly bias to align with."),
    (WEEKLY_ONLY, "WEEKLY ONLY — the Daily has not broken structure yet."),
)


def _side(direction) -> str:
    return getattr(direction, "value", str(direction) if direction else "")


def line_for(instrument: str, account) -> str:
    """One instrument's line. Short enough that 27 of them still read."""
    side = _side(getattr(account, "direction", None))
    state = getattr(account, "alignment", "")
    if state == NOT_ALIGNED:
        other = _side(getattr(account, "other_direction", None))
        return f"  {instrument:<8} {side:<8} (Weekly {other})"
    return f"  {instrument:<8} {side}"


def roll_call(label: str, heading: str, accounts: list[tuple]) -> str:
    """`accounts` is [(instrument, account_or_None), ...].

    Returns one message. Instruments with no bias are named but not
    detailed -- knowing which pairs to IGNORE today is half the point of
    a watchlist.
    """
    grouped = {key: [] for key, _ in GROUPS}
    no_bias = []
    for instrument, account in accounts:
        if account is None or getattr(account, "direction", None) is None:
            no_bias.append(instrument)
            continue
        state = getattr(account, "alignment", "")
        grouped.setdefault(state, []).append((instrument, account))

    lines = [f"{label} {heading}", ""]
    for key, title in GROUPS:
        rows = grouped.get(key) or []
        if not rows:
            continue
        lines.append(f"{title}  ({len(rows)})")
        lines += [line_for(instrument, account) for instrument, account in rows]
        lines.append("")

    if no_bias:
        lines.append(f"NO BIAS ({len(no_bias)}) — nothing to watch:")
        lines.append("  " + ", ".join(sorted(no_bias)))
        lines.append("")

    focus = len(grouped.get(ALIGNED) or [])
    lines.append(f"{focus} pair(s) with both timeframes agreeing.")
    return "\n".join(lines).rstrip()
