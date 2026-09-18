"""
The "storyline" gate: a cheap, higher-timeframe-only check for whether an
instrument is even worth running the full entry search on right now.

Why this exists
---------------
`run_backtest()` is the single source of truth for entry detection, and
the live loop deliberately calls it unmodified (see live_cache_sync.py's
docstring for that decision). But it re-derives EVERYTHING from full
history on every call, and the live loop was calling it once per
instrument on every H1 close -- 25 instruments x 2 styles x 24 closes a
day. On a 2-vCPU VPS that never finished an hour's work inside the hour,
so the bots fell hours behind and missed real setups (see
bot/OPERATIONS_LOG.md, 2026-08-26).

This module encodes how the strategy is actually traded by hand: you do
not re-analyse every pair every hour. You wait for the Daily to align
with the Weekly -- checking daily, not hourly. Once Daily is set you
watch the 4H. Only once the 4H aligns with the Daily do you drop to H1
looking for the confirmation entry. Pairs that are not forming anything
get a glance, not a full analysis.

So: `storyline_at()` answers "is this pair in the hunting stage?" using
ONLY Weekly/Daily/H4 data. That context changes only when a Weekly,
Daily, or H4 candle closes -- not on every H1 close -- so the caller
caches it (`HTFContext`) and rebuilds only on those closes. When the
answer is "still waiting", the whole H1 entry search is skipped.

The safety property this must have
----------------------------------
The gate is only allowed to be a PERFORMANCE filter, never a strategy
change. It must have no false negatives: if `run_backtest()` would have
produced a trade at some candle, the gate must have said "hunting" at
that candle's time. Anything else means the gate is silently suppressing
real signals, which is far worse than being slow.

That property is not asserted by hand-written fixtures -- it is tested
directly against real cached history in tests/test_live_strategy.py, by
running the real `run_backtest()` over years of data and checking the
gate was open at every single trade it produced.

Deliberately reuses runner.py's own private helpers rather than
reimplementing the alignment/bias rules here. Importing a private name
across modules is not lovely, but a second copy of these rules that
could drift from the validated ones is the exact failure mode this
project has already been bitten by, and drift is worse than coupling.
"""

import bisect
from dataclasses import dataclass

from backtest.engine.bias import (
    Confirmation, bias_at, confirmation_known_at, detect_confirmations, replay_bias,
    resolve_effective_bias,
)
from backtest.engine.key_levels import detect_key_levels
from backtest.engine.runner import (
    ALIGNMENT_LOOKBACK, BIAS_CONFIRMATION_WINDOW, _bootstrap_origin, _direction_lookup,
    _last_direction_at, _trim_to_recent_years, load_candles,
)
from backtest.engine.structure import Direction, StructureTracker

WAITING = "waiting_htf"
HUNTING = "hunting"


@dataclass(frozen=True)
class HTFContext:
    """Everything the gate needs, derived from Weekly/Daily/H4 only.

    `latest_h4_time` / `latest_daily_time` / `latest_weekly_time` record
    the newest candle of each timeframe this context was built from, so
    the caller can tell whether a rebuild is actually due yet."""
    instrument: str
    weekly_breakpoints: list
    daily_breakpoints: list
    weekly_confirmations: list
    daily_confirmations: list
    h4_confirmations: list
    h4_lookup: tuple
    latest_weekly_time: object
    latest_daily_time: object
    latest_h4_time: object


@dataclass(frozen=True)
class Storyline:
    """Where one instrument currently sits in the top-down sequence.

    stage == HUNTING means Daily and H4 both currently confirm the same
    direction AND the effective (highest-priority) bias agrees with it --
    i.e. the point at which a manual trader would drop to H1 looking for
    the entry. Anything else is WAITING, and no H1 work is warranted."""
    stage: str
    direction: Direction | None
    effective_tf: str | None
    aligned: tuple[str, ...]
    reason: str
    # When each timeframe's OWN most recent confirmation actually closed --
    # None if that timeframe never reached its own alignment check (e.g.
    # Daily/H4 disagreed, so Weekly was never even looked at). Added
    # 2026-08-30, direct request: "let me know if what's logged in is
    # current candle and not some past candle" -- the storyline log line
    # said e.g. "Weekly/Daily/H4 aligned bullish" with no way to tell
    # whether each of those was actually recent or was sitting near the
    # edge of ALIGNMENT_LOOKBACK.
    daily_confirmed_at: object = None
    h4_confirmed_at: object = None
    weekly_confirmed_at: object = None


def _latest_time(candles):
    return candles[-1].time if candles else None


def build_htf_context(instrument: str, source: str = "dukascopy", n: int = 2,
                       close_based_breakout: bool = True,
                       confirmation_window: int = BIAS_CONFIRMATION_WINDOW,
                       origin_kind: str = "sweep_break",
                       close_based_sweep_break: bool = False,
                       max_history_years: dict | None = None) -> HTFContext | None:
    """Derive the Weekly/Daily/H4 bias context. Returns None when there
    isn't enough structure to bootstrap a bias from -- the same condition
    that makes `run_backtest()` return no trades at all, so a None here
    is a legitimate "nothing to hunt", not an error.

    Costs roughly the Daily + H4 portion of a full run_backtest and, by
    design, touches no H1 data at all.

    `origin_kind`, `close_based_sweep_break` and `max_history_years` exist
    because the gate MUST compute bias the same way the engine it gates
    does. Until 2026-09-18 they did not: this function hardcoded a
    `valid_sweep_break` origin, wick-based sweep breaks, and uncapped
    history, while both live bots launch with `--origin-kind any
    --close-based-sweep-break --history-windows-config`. Different bias
    input, different answer -- so the gate could say WAITING at a candle
    where run_backtest produced a trade, which is exactly the false
    negative this module's own docstring says it must never have.

    The hardcoded origin had a worse failure mode than a disagreement.
    An instrument whose Daily history contained no `valid_sweep_break` at
    all returned None here and was gated off PERMANENTLY, while the
    engine under `origin_kind="any"` would have bootstrapped from the
    first confirmation and traded it. Before the 2026-09-18 structure
    latch fix, `valid_sweep_break` events were far rarer than they looked
    -- one direction could be dead for years -- so that was not a remote
    possibility.

    Defaults match the pre-2026-09-18 behavior so nothing changes for a
    caller that has not been updated; the orchestrator passes its real
    values."""
    try:
        daily = load_candles(source, instrument, "D")
        h4 = load_candles(source, instrument, "H4")
    except FileNotFoundError:
        return None
    if not daily or not h4:
        return None

    try:
        weekly = load_candles(source, instrument, "W")
    except FileNotFoundError:
        weekly = []

    # Same trailing-history caps run_backtest applies, for the same
    # reason: a bias built from a different amount of history is a
    # different bias.
    if max_history_years:
        daily = _trim_to_recent_years(daily, max_history_years.get("D"))
        weekly = _trim_to_recent_years(weekly, max_history_years.get("W"))
        h4 = _trim_to_recent_years(h4, max_history_years.get("H4"))
        if not daily or not h4:
            return None

    _confs = dict(close_based_breakout=close_based_breakout,
                  close_based_sweep_break=close_based_sweep_break)

    daily_events = StructureTracker(n, close_based_break=close_based_sweep_break).run(daily)
    daily_confirmations = detect_confirmations(daily, n, **_confs)
    # runner's own bootstrap, not a second copy of the rule -- see this
    # module's docstring on drift being worse than coupling.
    first_origin = _bootstrap_origin(daily_events, daily_confirmations, origin_kind)
    if first_origin is None:
        return None

    daily_levels = detect_key_levels(daily, n)
    weekly_confirmations = detect_confirmations(weekly, n, **_confs) if weekly else []
    h4_confirmations = detect_confirmations(h4, n, **_confs)

    daily_breakpoints = replay_bias(daily, daily_levels, h4_confirmations,
                                     first_origin.direction, "Daily",
                                     confirmation_window=confirmation_window)

    weekly_breakpoints = []
    if weekly:
        weekly_events = StructureTracker(n, close_based_break=close_based_sweep_break).run(weekly)
        weekly_first_origin = _bootstrap_origin(weekly_events, weekly_confirmations, origin_kind)
        if weekly_first_origin is not None:
            weekly_levels = detect_key_levels(weekly, n)
            weekly_breakpoints = replay_bias(weekly, weekly_levels, daily_confirmations,
                                              weekly_first_origin.direction, "Weekly",
                                              confirmation_window=confirmation_window)

    return HTFContext(
        instrument=instrument,
        weekly_breakpoints=weekly_breakpoints,
        daily_breakpoints=daily_breakpoints,
        weekly_confirmations=weekly_confirmations,
        daily_confirmations=daily_confirmations,
        h4_confirmations=h4_confirmations,
        h4_lookup=_direction_lookup(h4_confirmations),
        latest_weekly_time=_latest_time(weekly),
        latest_daily_time=_latest_time(daily),
        latest_h4_time=_latest_time(h4),
    )


def _recent_direction(confirmations: list[Confirmation], label: str, as_of_time):
    """The most recent confirmation on this timeframe at `as_of_time` (the
    whole Confirmation -- `.direction` and `.time` both, so callers get
    the confirmation's own date for free instead of a second lookup), or
    None if there isn't one inside that timeframe's ALIGNMENT_LOOKBACK
    window. Mirrors `_aligned_timeframes()`'s rule for a single timeframe,
    but bisects the sorted confirmation times instead of scanning the
    whole list."""
    if not confirmations:
        return None
    # known_at, not .time -- a Daily confirmation stamped 00:00 is not
    # readable until midnight the next day, and answering with it in
    # between is what let the gate open on a bar still forming
    # (2026-09-18 review, finding 1). The RECENCY window below still
    # measures from the confirmation's own candle, which is what
    # "how recent is this confirmation" means to a chart reader.
    ordered = sorted(confirmations, key=confirmation_known_at)
    times = [confirmation_known_at(c) for c in ordered]
    idx = bisect.bisect_right(times, as_of_time) - 1
    if idx < 0:
        return None
    latest = ordered[idx]
    if as_of_time - latest.time > ALIGNMENT_LOOKBACK[label]:
        return None
    return latest


def storyline_at(ctx: HTFContext, as_of_time) -> Storyline:
    """Where this instrument sits in the top-down sequence at
    `as_of_time`, using higher-timeframe context only.

    HUNTING requires exactly what `run_backtest()`'s own entry loop
    requires before it will consider any candidate: Daily and H4 must
    each independently confirm the same direction (its multi-timeframe
    ALIGNMENT gate), and the effective highest-priority bias must agree
    with that direction. Weekly is recorded when it also aligns -- a
    probability booster there, not a gate -- exactly as in the entry
    loop."""
    daily_conf = _recent_direction(ctx.daily_confirmations, "Daily", as_of_time)
    h4_conf = _recent_direction(ctx.h4_confirmations, "H4", as_of_time)

    if daily_conf is None or h4_conf is None:
        missing = "Daily" if daily_conf is None else "H4"
        return Storyline(WAITING, None, None, (),
                          f"no recent {missing} confirmation -- nothing to align to yet",
                          daily_confirmed_at=daily_conf.time if daily_conf else None,
                          h4_confirmed_at=h4_conf.time if h4_conf else None)
    daily_dir, h4_dir = daily_conf.direction, h4_conf.direction
    if daily_dir != h4_dir:
        return Storyline(WAITING, None, None, (),
                          f"Daily ({daily_dir.value}) and H4 ({h4_dir.value}) disagree -- "
                          "waiting for the 4H to come round to the Daily",
                          daily_confirmed_at=daily_conf.time, h4_confirmed_at=h4_conf.time)

    direction = daily_dir
    weekly_bias = bias_at(ctx.weekly_breakpoints, as_of_time) if ctx.weekly_breakpoints else None
    daily_bias = bias_at(ctx.daily_breakpoints, as_of_time)
    h4_bias = _last_direction_at(ctx.h4_lookup, as_of_time)
    effective, effective_tf = resolve_effective_bias(
        {"Weekly": weekly_bias, "Daily": daily_bias, "H4": h4_bias}
    )
    if effective is None:
        return Storyline(WAITING, None, None, (), "no active bias on any higher timeframe",
                          daily_confirmed_at=daily_conf.time, h4_confirmed_at=h4_conf.time)
    if effective != direction:
        return Storyline(WAITING, None, effective_tf, (),
                          f"{effective_tf} bias ({effective.value}) opposes the aligned "
                          f"Daily/H4 direction ({direction.value}) -- induced-move trap, not a setup",
                          daily_confirmed_at=daily_conf.time, h4_confirmed_at=h4_conf.time)

    aligned = ["Daily", "H4"]
    weekly_conf = _recent_direction(ctx.weekly_confirmations, "Weekly", as_of_time)
    weekly_confirmed_at = None
    if weekly_conf is not None and weekly_conf.direction == direction:
        aligned.insert(0, "Weekly")
        weekly_confirmed_at = weekly_conf.time

    return Storyline(HUNTING, direction, effective_tf, tuple(aligned),
                      f"{'/'.join(aligned)} aligned {direction.value} -- watching H1 for the entry",
                      daily_confirmed_at=daily_conf.time, h4_confirmed_at=h4_conf.time,
                      weekly_confirmed_at=weekly_confirmed_at)


def needs_rebuild(ctx: HTFContext | None, latest_weekly_time, latest_daily_time,
                   latest_h4_time) -> bool:
    """True when a Weekly, Daily or H4 candle has closed since `ctx` was
    built, so the cached context is stale.

    H4 counts because the Daily cascade's flip test consumes H4
    confirmations (`replay_bias(daily, ..., h4_confirmations, ...)`) -- a
    new H4 confirmation can therefore change a Daily bias reading, so a
    rebuild on Daily closes alone would not be sound. In practice that
    still means ~7 rebuilds a day instead of the 24 full run_backtest
    calls this replaces."""
    if ctx is None:
        return True
    return (ctx.latest_weekly_time != latest_weekly_time
            or ctx.latest_daily_time != latest_daily_time
            or ctx.latest_h4_time != latest_h4_time)
