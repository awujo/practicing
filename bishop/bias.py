"""First supported causal Bishop origin/confirmation routes (D01,D02,D05).

Supported: first-use KL rejection OR previous-candle extreme sweep, followed by
closed next-lower-TF breakout beyond a frozen pre-touch local close-turn. Source:
v9@76-151,574-672; v17@1248-1272; Bishop bias2@408.5-478.4.

Explicit provisional choices: local close-turn structure; exact price touches;
first-use KLs (a touch or invalidating close retires that original role); nearest
known opposing origin-TF KL as a frozen destination candidate. No implicit
impulse threshold or freshness reset. A target here is ORIGIN_KL, not ERL.

NOT YET SUPPORTED: role-flipped/reused KL origin, W-level/D-origin fallback,
engulf->further-TF cascade, full structural swing grading, active-story lifecycle,
counterweekly eligibility filtering or entry/execution. Engulf alone never
confirms/changes a story. These limitations must remain visible in reports.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .price_action import _time, levels, validated_bars
from .structure import turning_points, events as structure_events

LADDERS = {"M": "W", "W": "D", "D": "H4", "H4": "H1"}
UNSUPPORTED_ROUTES = ("role_flipped_or_reused_origin", "weekly_level_daily_fallback",
                      "engulf_then_further_tf", "full_story_lifecycle", "counterweekly_policy")


@dataclass(frozen=True)
class Candidate:
    side: str
    origin_tf: str
    level_tf: str
    origin_start: pd.Timestamp
    origin_at: pd.Timestamp
    level: float
    level_kind: str
    level_available_at: pd.Timestamp
    trigger: str
    level_mode: str = "exact_junction"


@dataclass(frozen=True)
class Story:
    side: str
    origin_tf: str
    level_tf: str
    confirmation_tf: str
    origin_at: pd.Timestamp
    available_at: pd.Timestamp
    level: float
    level_kind: str
    trigger: str
    confirmation_kind: str
    confirmation_reference: float
    reference_available_at: pd.Timestamp
    confirmation_at: pd.Timestamp
    target: float | None
    target_available_at: pd.Timestamp | None
    target_kind: str
    target_tf: str
    policy: str = "first_touch_local_turn_nearest_known_kl"
    level_mode: str = "exact_junction"


def _starts(raw, frame):
    if "start" not in raw.columns:
        # Without candle-start metadata, do not guess in-bar event ordering.
        return {at: at for at in frame.index}
    starts = [_time(x, "origin start") for x in raw["start"]]
    if any(start >= end for start, end in zip(starts, frame.index)):
        raise ValueError("origin start must precede its end")
    return dict(zip(frame.index, starts))


def find_candidates(origin_bars, *, origin_tf="D", level_bars=None, level_tf=None, level_mode="exact_junction", as_of=None):
    """Closed origin anchors, including unconfirmed leans, without future data."""
    if origin_tf not in LADDERS:
        raise ValueError("unsupported origin timeframe")
    frame = validated_bars(origin_bars, as_of=as_of)
    starts = _starts(origin_bars, frame)
    if level_bars is not None and level_tf != origin_tf:
        raise ValueError("cross-timeframe level origins require the not-yet-supported fallback route")
    source = frame if level_bars is None else validated_bars(level_bars, as_of=as_of)
    known = levels(source, as_of=as_of, level_mode=level_mode)
    consumed, out = set(), []
    for i, (at, row) in enumerate(frame.iterrows()):
        for number, level in enumerate(known):
            if number in consumed or level.available_at >= at:
                continue
            touched = row.low <= level.price <= row.high
            invalidated = row.close < level.price if level.side == "BUY" else row.close > level.price
            if touched or invalidated:
                consumed.add(number)
            rejected = touched and (row.close > level.price if level.side == "BUY" else row.close < level.price)
            if rejected:
                out.append(Candidate(level.side, origin_tf, origin_tf, starts[at], at,
                                     level.price, level.kind, level.available_at, "KL_REJECTION", level_mode))
        if i:
            previous = frame.iloc[i-1]
            if row.low < previous.low and row.close > previous.low:
                out.append(Candidate("BUY", origin_tf, origin_tf, starts[at], at,
                                     float(previous.low), "PREVIOUS_LOW", frame.index[i-1], "CANDLE_SWEEP", level_mode))
            if row.high > previous.high and row.close < previous.high:
                out.append(Candidate("SELL", origin_tf, origin_tf, starts[at], at,
                                     float(previous.high), "PREVIOUS_HIGH", frame.index[i-1], "CANDLE_SWEEP", level_mode))
    return out


def _touch(candidate, lower):
    rows = lower[(lower.index > candidate.origin_start) & (lower.index <= candidate.origin_at)]
    for at, bar in rows.iterrows():
        if candidate.trigger == "KL_REJECTION":
            touched = bar.low <= candidate.level <= bar.high
        else:
            touched = bar.low < candidate.level if candidate.side == "BUY" else bar.high > candidate.level
        if touched:
            return at
    # Missing explicit starts means confirmation must follow origin closure.
    return candidate.origin_at


def find_stories(origin_bars, confirmation_bars, *, origin_tf="D", confirmation_tf="H4", level_mode="exact_junction", as_of=None):
    """Return immutable confirmed stories; no future outcomes mutate old records.

    Same-day confirmation inside an origin bar requires explicit origin ``start``
    metadata and a lower-TF touch strictly before breakout. Eligibility is MAX
    of the origin close and confirming close. Without starts, only later breaks
    qualify. A forming or mere engulfing candle is never a confirmation.
    """
    if LADDERS.get(origin_tf) != confirmation_tf:
        raise ValueError("confirmation timeframe must be the supported next-lower ladder")
    origin = validated_bars(origin_bars, as_of=as_of)
    lower = validated_bars(confirmation_bars, as_of=as_of)
    points = turning_points(lower, as_of=as_of)
    lower_closes = lower.close.to_numpy()
    references = []
    for point in points:
        start = lower.index.get_loc(point.available_at) + 1
        beyond = lower_closes[start:] > point.price if point.kind == "H" else lower_closes[start:] < point.price
        hits = np.flatnonzero(beyond)
        broken_at = lower.index[start + hits[0]] if len(hits) else None
        references.append((point, broken_at))
    sweeps = [e for e in structure_events(lower, as_of=as_of) if e.kind == "SWEEP"]
    destinations = levels(origin, as_of=as_of, level_mode=level_mode)
    destination_breaks = {}
    for destination in destinations:
        later = origin[origin.index > destination.available_at]
        invalid = later.close > destination.price if destination.side == "SELL" else later.close < destination.price
        destination_breaks[destination] = later.index[invalid][0] if invalid.any() else None
    out = []
    for candidate in find_candidates(origin_bars, origin_tf=origin_tf, level_mode=level_mode, as_of=as_of):
        touch = _touch(candidate, lower)
        ref_kind = "H" if candidate.side == "BUY" else "L"
        refs = []
        for point, broken_at in references:
            if point.kind == ref_kind and point.available_at < touch and (broken_at is None or broken_at > touch):
                refs.append(point)
        if not refs:
            continue
        reference = refs[-1]
        previous = np.r_[np.nan, lower_closes[:-1]]
        if candidate.side == "BUY":
            crossings = (previous <= reference.price) & (lower_closes > reference.price)
        else:
            crossings = (previous >= reference.price) & (lower_closes < reference.price)
        indices = np.flatnonzero(crossings & (lower.index > touch))
        if not len(indices):
            continue
        number = int(indices[0])
        at, row = lower.index[number], lower.iloc[number]
        available = max(candidate.origin_at, at)
        # A closed origin invalidation before delayed confirmation retires it.
        before = origin[(origin.index > candidate.origin_at) & (origin.index <= available)]
        invalidated = (before.close < candidate.level).any() if candidate.side == "BUY" else (before.close > candidate.level).any()
        if invalidated:
            continue
        # Target selection uses only origin levels known at first eligibility.
        wanted_side = "SELL" if candidate.side == "BUY" else "BUY"
        eligible_close = float(lower.loc[lower.index <= available, "close"].iloc[-1])
        targets = [p for p in destinations if p.available_at <= available and p.side == wanted_side
                   and (destination_breaks[p] is None or destination_breaks[p] > available)
                   and (p.price > eligible_close if candidate.side == "BUY" else p.price < eligible_close)]
        target = min(targets, key=lambda p: abs(p.price-eligible_close)) if targets else None
        sweep = any(e.side == candidate.side and touch <= e.available_at < at
                    and e.reference_available_at < touch for e in sweeps)
        out.append(Story(candidate.side, origin_tf, candidate.level_tf, confirmation_tf,
                         candidate.origin_at, available, candidate.level, candidate.level_kind,
                         candidate.trigger, "SWEEP_BOS" if sweep else "BREAKOUT", reference.price,
                         reference.available_at, at, target.price if target else None,
                         target.available_at if target else None, "ORIGIN_KL", origin_tf, level_mode=level_mode))
    return out
