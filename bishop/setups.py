"""Causal setup formation, not fills or a complete Bishop entry policy.

Sources: core video-14@456-658 describes the alternative engulf/A-V retest
and broken open-close retest paths; video-13@307-332,2142-2157 discusses
protecting the relevant wick with 0.5/1 pip padding. Bishop's ERL target
preference is preserved when an upstream detector supplies an ERL context.

Numerical choices remain explicit: body engulf means an opposite candle with
a close strictly beyond the previous body's open. The default junction must be
exact. Explicit ``close_reference`` instead retains the first candle's close
across opening gaps, consistently with ``price_action.levels``; no pip tolerance
or gap midpoint is inferred. This is a separate operational policy.
The structural stop protects both engulf candles, or the entire OC-to-break
sequence. These are conservative implementations of the checked descriptions,
not proof they reproduce every teaching chart. No impulse/FVG threshold or
extra-IRL condition is invented. Returned objects are pending setup FORMATIONS;
formation-candle fills, historical execution and expiry belong to execution.
"""
from dataclasses import dataclass
from decimal import Decimal
import heapq
import math

from .price_action import _time, validated_bars

SUPPORTED_MODELS = ("engulf_retest", "oc_break_retest")


def _finite(value, name, *, positive=False):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))
    return result


@dataclass(frozen=True)
class Context:
    """Frozen, already confirmed context supplied by the bias/liquidity layer.

    ``target_available_at`` must not follow context availability: a later-found
    target requires a newly observable context, not a rewrite of earlier setups.
    ORIGIN_KL is a story destination, deliberately not relabelled nearest ERL.
    """
    side: str
    available_at: object
    origin_tf: str
    target: float
    target_available_at: object
    target_kind: str
    target_tf: str
    expires_at: object = None

    def __post_init__(self):
        if self.side not in ("BUY", "SELL"):
            raise ValueError("context side must be BUY or SELL")
        for name in ("origin_tf", "target_tf"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a nonempty timeframe")
        if self.target_kind not in ("ERL", "ORIGIN_KL"):
            raise ValueError("target_kind must explicitly be ERL or ORIGIN_KL")
        available = _time(self.available_at, "context available_at")
        target_at = _time(self.target_available_at, "target available_at")
        if target_at > available:
            raise ValueError("target cannot be supplied before it is known")
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "target_available_at", target_at)
        object.__setattr__(self, "target", _finite(self.target, "target", positive=True))
        if self.expires_at is not None:
            expiry = _time(self.expires_at, "context expires_at")
            if expiry <= available:
                raise ValueError("context expiry must follow availability")
            object.__setattr__(self, "expires_at", expiry)


@dataclass(frozen=True)
class RiskProfile:
    """Explicit stop policy. Defaults are choices, not example expectations.

    ``structural_wick`` protects the observed pattern extreme plus padding.
    ``fixed_pips`` is the separate owner operating experiment; it never
    overwrites a source's structural stop or changes the supplied target.
    """
    mode: str
    pip_size: float
    buffer_pips: float = 0.5
    fixed_stop_pips: float = 11.0

    def __post_init__(self):
        if self.mode not in ("structural_wick", "fixed_pips"):
            raise ValueError("invalid stop profile")
        object.__setattr__(self, "pip_size", _finite(self.pip_size, "pip_size", positive=True))
        padding = _finite(self.buffer_pips, "buffer_pips")
        if padding < 0:
            raise ValueError("buffer_pips must be nonnegative")
        object.__setattr__(self, "buffer_pips", padding)
        object.__setattr__(self, "fixed_stop_pips", _finite(self.fixed_stop_pips, "fixed_stop_pips", positive=True))


@dataclass(frozen=True)
class Setup:
    model: str
    side: str
    tf: str
    profile: str
    entry: float
    stop: float
    target: float
    formed_at: object
    available_at: object
    context_available_at: object
    origin_tf: str
    target_kind: str
    target_tf: str
    target_available_at: object
    reference_at: object
    level_mode: str

    @property
    def reward_risk(self):
        return abs(self.target - self.entry) / abs(self.entry - self.stop)


def _setup(model, frame, first, last, entry, context, tf, profile, level_mode):
    """Build from a causal pattern slice, never a source fixture or later wick."""
    low = float(frame["low"].iloc[first:last + 1].min())
    high = float(frame["high"].iloc[first:last + 1].max())
    sign = 1 if context.side == "BUY" else -1
    if profile.mode == "structural_wick":
        reference = low if sign > 0 else high
        stop = Decimal(str(reference)) - sign * Decimal(str(profile.buffer_pips)) * Decimal(str(profile.pip_size))
    else:
        stop = Decimal(str(entry)) - sign * Decimal(str(profile.fixed_stop_pips)) * Decimal(str(profile.pip_size))
    stop = float(stop)
    target = context.target
    if stop <= 0 or not (stop < entry < target if sign > 0 else target < entry < stop):
        return None
    at = frame.index[last]
    return Setup(model, context.side, tf, profile.mode, float(entry), stop, target,
                 at, at, context.available_at, context.origin_tf, context.target_kind,
                 context.target_tf, context.target_available_at, frame.index[first], level_mode)


def detect_setups(bars, context, *, tf, profile, as_of=None, models=SUPPORTED_MODELS,
                  level_mode="exact_junction"):
    """Return immutable pending formations on completed, end-indexed bars.

    The context must already be confirmed. Patterns before its availability
    are never retrospectively admitted. The context's frozen target retires
    after its first observed touch at/after context availability; this explicit
    conservative policy prevents placing fresh orders toward spent liquidity.

    OC candidates are consumed on their first directional close through,
    including before context exists. A later context cannot resurrect an old
    break. Heap ordering processes each OC once rather than rescanning every
    historical level on every candle. Retest fills are intentionally absent.
    """
    if not isinstance(context, Context) or not isinstance(profile, RiskProfile):
        raise ValueError("explicit Context and RiskProfile are required")
    if not isinstance(tf, str) or not tf.strip():
        raise ValueError("tf must be a nonempty timeframe")
    if level_mode not in ("exact_junction", "close_reference"):
        raise ValueError("level_mode must be exact_junction or close_reference")
    models = tuple(models)
    if not models or len(set(models)) != len(models) or any(m not in SUPPORTED_MODELS for m in models):
        raise ValueError("models must select unique supported entry paths")
    frame = validated_bars(bars, as_of=as_of)
    if frame.empty:
        return []
    values = frame.to_numpy()
    # validated_bars columns are open, high, low, close.
    direction = 1 if context.side == "BUY" else -1
    oc_heap, found = [], []
    target_alive = True
    for i, (opened, high, low, close) in enumerate(values):
        at = frame.index[i]
        if context.expires_at is not None and at >= context.expires_at:
            break
        eligible = at >= context.available_at and (context.expires_at is None or at < context.expires_at)
        if eligible and (high >= context.target if direction > 0 else low <= context.target):
            target_alive = False
            break  # This frozen context can never authorize another setup.
        # Consume every first close through an old OC, whether or not context
        # is already known. A same-time new OC is pushed only afterwards.
        while oc_heap and direction * close > oc_heap[0][0]:
            _, first, level = heapq.heappop(oc_heap)
            if eligible and target_alive and direction * (close - opened) > 0:
                setup = _setup("oc_break_retest", frame, first, i, level, context, tf, profile, level_mode)
                if setup:
                    found.append(setup)
        if not i:
            continue
        previous_open, _, _, previous_close = values[i - 1]
        joined = previous_close == opened if level_mode == "exact_junction" else True
        current_direction = direction * (close - opened)
        previous_direction = direction * (previous_close - previous_open)
        if ("engulf_retest" in models and eligible and target_alive and joined
                and previous_direction < 0 and current_direction > 0
                and direction * (close - previous_open) > 0):
            setup = _setup("engulf_retest", frame, i - 1, i, previous_close, context, tf, profile, level_mode)
            if setup:
                found.append(setup)
        if ("oc_break_retest" in models and joined
                and previous_direction < 0 and current_direction < 0
                and (level_mode == "exact_junction" or direction * (close - previous_close) < 0)):
            heapq.heappush(oc_heap, (direction * previous_close, i - 1, float(previous_close)))
    return sorted(found, key=lambda s: (s.available_at, s.model, s.reference_at, s.entry))
