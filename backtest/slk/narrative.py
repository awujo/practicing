"""
The story behind the bias, in English.

Operator, 2026-09-25:

    "just add english ... if you tell me the time, if it is a breakout,
     if it is a rejection, if it is a liquidity sweep ... did the
     previous day or week low get swept and the high is standing, a
     single candle liquidity ... I'm reading it and I will understand,
     okay this is your storyline, this is the story behind your bias."

So a message from the SLK side never says "bullish" and stop. It says
which timeframe did what, to which price, and what that leaves price
expected to do -- because that is the thing a person can hold against a
chart and disagree with.

WHY THIS IS A SEPARATE MODULE

It recomputes nothing. Every sentence below is built from an `Evidence`
that the cascade recorded at the moment the event happened. A narrator
that worked things out for itself would be a second strategy wearing a
description's clothes, and it would eventually contradict the engine it
claims to be reporting -- which is the exact failure this project has
already paid for twice.

TWO ENGINES, TWO STORIES, AND THEY ARE NOT MERGED

The old bot keeps its own bias and its own words, untouched -- operator:
"my old system, don't change it ... I want to be using two of them as
confluence." These sentences are the SLK side only, and every message is
labelled so the two can never be mistaken for each other.
"""

from __future__ import annotations

from ..engine.structure import Direction


def _side(direction) -> str:
    return getattr(direction, "value", str(direction))


def _when(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return text[:16]


def sweep_sentence(evidence, timeframe: str) -> str:
    """A previous period's liquidity taken, with the other side standing.

    This is bias built with LIQUIDITY rather than with a key level --
    Bishop's own checklist, "previous daily weekly low sweep, what's
    daily breakout to the upside" (daily-routine t=534-540). The half
    that matters and is easy to leave out is the side STILL STANDING:
    that is what makes the expansion towards it the thing to expect.
    """
    taken = "low" if evidence.taken_kind == "low" else "high"
    other = "high" if taken == "low" else "low"
    text = (f"{timeframe} swept a previous {timeframe.lower()} {taken}"
            f" at {evidence.taken:g}")
    if evidence.standing is not None:
        text += f", and that candle's {other} at {evidence.standing:g} is still standing"
    text += (f" — so the liquidity taken is internal range, and price is "
             f"expected to expand {'up' if evidence.direction == Direction.BULLISH else 'down'}"
             f" towards the {other}.")
    return text


def rejection_sentence(evidence, timeframe: str) -> str:
    """A key level reached and closed back away from."""
    where = f" at {evidence.level:g}" if evidence.level is not None else ""
    used_for = "buys" if evidence.direction == Direction.BULLISH else "sells"
    return (f"{timeframe} rejected from its key level{where} — price reached it "
            f"and closed back away, which is what makes it a level for {used_for}.")


def confirmed_sentence(lower: str, direction) -> str:
    """The second half of either route: the next timeframe down agreeing."""
    way = "to the upside" if direction == Direction.BULLISH else "to the downside"
    return f"{lower} then broke structure {way}, confirming it."


def bias_story(evidence, higher: str, lower: str) -> list[str]:
    """The whole reason one rung holds a bias, as lines of English."""
    if evidence is None:
        return []
    if evidence.kind == "sweep":
        first = sweep_sentence(evidence, higher)
    else:
        first = rejection_sentence(evidence, higher)
    lines = [f"  {first}"]
    lines.append(f"  {confirmed_sentence(lower, evidence.direction)}")
    if evidence.at is not None:
        lines.append(f"  (as of {_when(evidence.at)})")
    return lines


def liquidity_taken_sentence(instrument: str, direction, price: float,
                             level_price: float | None,
                             timeframe: str = "H4") -> list[str]:
    """Single-candle liquidity taken on the setup timeframe.

    The operator asked for this one by name: "single candle liquidity has
    been taken, okay, look for your confirmation". It is the moment the
    setup becomes live, and the moment to go and look.
    """
    kind = "low" if direction == Direction.BULLISH else "high"
    lines = [
        f"{timeframe} single candle liquidity has been taken — the {kind} "
        f"at {price:g} went.",
    ]
    if level_price is not None:
        lines.append(f"The nearest key level to it is {level_price:g}, and that "
                      f"is the one being played.")
    lines.append("Now look for your confirmation on H1.")
    return lines


def setup_story(instrument: str, direction, liquidity: float,
                level_price: float, rejected: bool = True) -> list[str]:
    """Liquidity taken AND the key level played -- the full SLK setup."""
    kind = "low" if direction == Direction.BULLISH else "high"
    lines = [
        f"  single candle liquidity taken: the {kind} at {liquidity:g}",
        f"  nearest key level to it: {level_price:g}",
    ]
    if rejected:
        lines.append("  price has played that level and rejected from it.")
    else:
        lines.append("  waiting for price to reach that level and reject.")
    return lines


def confirmation_story(form: str, entry: float, stop: float,
                       target: float | None) -> list[str]:
    """What the H1 confirmation is, in the course's own vocabulary."""
    described = {
        "engulf": "an open-close key level was closed through, and price has "
                  "come back to it",
        "sweep_break": "price swept its own low and then broke structure the "
                       "other way — his highest-rated entry",
        "breakout": "price broke the minor structure the reaction left behind",
        "inducement": "the candle after the engulf became the liquidity, price "
                      "took it, then played the level",
    }.get(form, form)

    lines = [f"  {form}: {described}.",
             f"  entry {entry:g}, stop {stop:g}"]
    if target is not None:
        risk = abs(entry - stop)
        rr = abs(target - entry) / risk if risk else 0.0
        lines.append(f"  target {target:g}, which is {rr:.1f}R away")
    else:
        lines.append("  no external liquidity standing as a target")
    return lines
