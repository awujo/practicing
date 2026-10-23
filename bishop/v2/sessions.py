"""Explicit local-wall-clock session liquidity; no inferred Asian hours.

Sessions are [start, end), weekdays identify the local START date (Monday=0).
Overnight/end==start sessions finish on the next local date. UTC expected
slots come from the declared instrument calendar. Missing bars, unavailable
bars, nonaligned boundaries and DST ambiguity produce diagnostics, never a
partial high/low. Ambiguous boundaries need explicit dst_fold=0 or 1;
nonexistent boundaries are rejected rather than shifted silently.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from types import MappingProxyType
from collections.abc import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .aggregation import expected_slots, is_open, minutes
from .types import Bar, Instrument, Liquidity, StrategyPolicy, stable_id, utc


@dataclass(frozen=True)
class SessionResult:
    liquidity: tuple[Liquidity, ...]
    diagnostics: tuple[Mapping, ...]


def _immutable(value):
    if isinstance(value, Mapping):
        return MappingProxyType({k: _immutable(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_immutable(v) for v in value)
    return value


def _wall(day: date, wall: time, zone: ZoneInfo, fold):
    naive = datetime.combine(day, wall)
    possibilities = []
    for choice in (0, 1):
        local = naive.replace(tzinfo=zone, fold=choice)
        converted = local.astimezone(timezone.utc)
        if converted.astimezone(zone).replace(tzinfo=None) == naive:
            possibilities.append((choice, converted))
    distinct = {value for _, value in possibilities}
    if not distinct:
        raise ValueError("NONEXISTENT_LOCAL_BOUNDARY")
    if len(distinct) > 1:
        if fold is None:
            raise ValueError("AMBIGUOUS_LOCAL_BOUNDARY")
        return next(value for choice, value in possibilities if choice == fold)
    return possibilities[0][1]


def _time(value):
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError("session wall times must use HH:MM")
    try:
        return time(int(value[:2]), int(value[3:]))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid session wall time") from exc


def collect_sessions(bars, instrument: Instrument, as_of, sessions, *,
                     calendar=None, target_tf="H4", policy=StrategyPolicy()) -> SessionResult:
    """Build complete-session HIGH/LOW pools plus explicit skipped diagnostics.

    `sessions` is a manifest list of {id, timezone, start, end, weekdays?}.
    Optional `tf` assigns the output reference timeframe, and `dst_fold` resolves
    ambiguous local boundaries. `calendar` accepts the same explicit calendar
    descriptor as aggregation; absent override uses instrument.calendar_id.
    Empty sessions is valid and generates no guessed session configuration.
    """
    rows = tuple(bars)
    clock = utc(as_of)
    if not isinstance(instrument, Instrument):
        raise ValueError("explicit Instrument required")
    calendar = instrument.calendar_id if calendar is None else calendar
    # Validate even when an empty feed cannot furnish a session.
    is_open(clock, calendar)
    specifications = []
    ids = set()
    for specification in sessions:
        if not isinstance(specification, Mapping) or any(k not in specification for k in ("id", "timezone", "start", "end")):
            raise ValueError("session requires id, timezone, start, end")
        sid = specification["id"]
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError("session IDs must be nonempty and unique")
        ids.add(sid)
        try:
            zone = ZoneInfo(specification["timezone"])
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise ValueError("explicit IANA session timezone required") from exc
        begin, finish = _time(specification["start"]), _time(specification["end"])
        days = tuple(specification.get("weekdays", range(7)))
        if any(isinstance(d, bool) or not isinstance(d, int) or d not in range(7) for d in days):
            raise ValueError("weekdays must be integers Monday=0 through Sunday=6")
        fold = specification.get("dst_fold")
        if fold is not None and (isinstance(fold, bool) or fold not in (0, 1)):
            raise ValueError("dst_fold must be 0 or 1")
        tf = specification.get("tf", target_tf)
        minutes(tf)  # validate declared output timeframe, including D/W/M
        specifications.append((dict(specification), zone, begin, finish, days, fold, tf))
    if not rows:
        diagnostics = tuple(_immutable({"session_id": s[0]["id"], "status": "EMPTY_INPUT"}) for s in specifications)
        return SessionResult((), diagnostics)
    if any(not isinstance(b, Bar) for b in rows):
        raise ValueError("sessions require Bar records")
    base_tf = rows[0].tf
    base_minutes = minutes(base_tf)
    if base_minutes is None:
        raise ValueError("intraday base data required for sessions")
    step = timedelta(minutes=base_minutes)
    for i, bar in enumerate(rows):
        if bar.instrument != instrument.symbol or bar.tf != base_tf:
            raise ValueError("mixed session instruments/timeframes")
        if bar.end-bar.start != step:
            raise ValueError("session input has incorrect base duration")
        if (bar.start.timestamp() % step.total_seconds()) != 0:
            raise ValueError("session base bars must be UTC duration aligned")
        if i and rows[i-1].end > bar.start:
            raise ValueError("duplicate, overlapping or unordered session bars")
        if not is_open(bar.start, calendar):
            raise ValueError("session input outside declared calendar")
    available = {b.start: b for b in rows if b.complete and b.end <= clock and b.available_at <= clock}
    pools, diagnostics = [], []
    for specification, zone, begin, finish, days, fold, tf in specifications:
        first_day = rows[0].start.astimezone(zone).date()-timedelta(days=1)
        last_day = clock.astimezone(zone).date()
        day = first_day
        while day <= last_day:
            if day.weekday() not in days:
                day += timedelta(days=1)
                continue
            details = {"session_id": specification["id"], "local_start_date": day.isoformat(),
                       "timezone": zone.key, "boundary_policy": "LOCAL_WALL_REJECT_NONEXISTENT_V1",
                       "dst_fold": fold, "calendar": calendar, "base_tf": base_tf}
            try:
                start = _wall(day, begin, zone, fold)
                end_day = day+timedelta(days=1) if finish <= begin else day
                end = _wall(end_day, finish, zone, fold)
                if end <= start:
                    raise ValueError("NONPOSITIVE_SESSION")
            except ValueError as exc:
                diagnostics.append(_immutable({**details, "status": str(exc)}))
                day += timedelta(days=1)
                continue
            details.update(start=start.isoformat(), end=end.isoformat())
            if end <= rows[0].start or start > clock:
                day += timedelta(days=1)
                continue
            if end > clock:
                diagnostics.append(_immutable({**details, "status": "FORMING"}))
                day += timedelta(days=1)
                continue
            if any(bound.timestamp() % step.total_seconds() for bound in (start, end)):
                diagnostics.append(_immutable({**details, "status": "UNRESOLVED_RESOLUTION"}))
                day += timedelta(days=1)
                continue
            boundaries = ()
            if isinstance(calendar, Mapping):
                boundaries = tuple(utc(point) for name in ("open_intervals", "closed_intervals")
                                   for interval in calendar.get(name, ()) for point in interval)
            if any(start < point < end and point.timestamp() % step.total_seconds() for point in boundaries):
                diagnostics.append(_immutable({**details, "status": "UNRESOLVED_CALENDAR_RESOLUTION"}))
                day += timedelta(days=1)
                continue
            wanted = tuple(expected_slots(start, end, base_tf, calendar))
            missing = tuple(slot for slot in wanted if slot not in available)
            if not wanted or missing:
                diagnostics.append(_immutable({**details, "status": "MISSING_SLOTS" if missing else "CALENDAR_CLOSED",
                                                     "missing_slots": tuple(s.isoformat() for s in missing)}))
                day += timedelta(days=1)
                continue
            evidence = tuple(available[slot] for slot in wanted)
            # Calendar partial slots are not a license to include an OHLC bar
            # straddling a calendar closure: its extrema cannot be separated.
            if any(b.end > end or not is_open(b.end-timedelta(microseconds=1), calendar) for b in evidence):
                diagnostics.append(_immutable({**details, "status": "CROSSING_CALENDAR_BOUNDARY"}))
                day += timedelta(days=1)
                continue
            known_at = max(end, *(b.available_at for b in evidence))
            details.update(status="COMPLETE", session_manifest_id=stable_id("session_spec", specification),
                           source_bar_ids=tuple(b.id for b in evidence), standing_at_formation=True)
            for kind, price in (("HIGH", max(b.high_ticks for b in evidence)),
                                ("LOW", min(b.low_ticks for b in evidence))):
                pools.append(Liquidity(id=stable_id("session_pool", policy.id, instrument.symbol,
                    tf, specification, calendar, start, end, kind, tuple(b.id for b in evidence)),
                    instrument=instrument.symbol, tf=tf, kind=kind, price_ticks=price,
                    formed_at=end, available_at=known_at, form="SESSION",
                    bar_ids=tuple(b.id for b in evidence), policy_id=policy.id, details=details))
            diagnostics.append(_immutable(details))
            day += timedelta(days=1)
    return SessionResult(tuple(sorted(pools, key=lambda p: (p.available_at, p.id))), tuple(diagnostics))
