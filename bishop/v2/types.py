"""Shared causal records for the complete offline/paper build.

Prices are instrument ticks. Clock intervals describe what OHLC actually
establishes; availability is separate from occurrence. These records contain
no IO, broker integration, fixture lookup or outcome-dependent identifiers.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


def utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("an aware timestamp is required")
    return value.astimezone(timezone.utc)


def jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return utc(value).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return {f.name: jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    return value


def stable_id(namespace: str, *causes: Any) -> str:
    payload = json.dumps(jsonable(causes), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return namespace + "_" + sha256(payload.encode()).hexdigest()[:24]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        raise ValueError("unordered evidence is not allowed")
    return value


def _ticks(*values):
    if any(value is not None and type(value) is not int for value in values):
        raise ValueError("prices must use integer ticks")


def _side(side: str | None) -> None:
    if side not in (None, "BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")


@dataclass(frozen=True)
class Clock:
    occurred_from: datetime
    occurred_to: datetime
    available_at: datetime
    precision: str = "BAR"

    def __post_init__(self):
        for name in ("occurred_from", "occurred_to", "available_at"):
            object.__setattr__(self, name, utc(getattr(self, name)))
        if not self.occurred_from <= self.occurred_to <= self.available_at:
            raise ValueError("occurrence must precede availability")


@dataclass(frozen=True)
class Instrument:
    symbol: str
    tick_size: Decimal | str
    distance_unit: Decimal | str
    calendar_id: str = "fx_ny_v1"
    anchor_id: str = "ny17_wall_v2"
    price_basis: str = "BID"
    source_id: str = "declared_local_input"
    venue: str = "UNSPECIFIED"

    def __post_init__(self):
        for name in ("tick_size", "distance_unit"):
            value = Decimal(str(getattr(self, name)))
            if not value.is_finite() or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, value)
        if self.price_basis not in ("BID", "ASK", "MID", "BID_ASK"):
            raise ValueError("explicit price basis required")

    def to_ticks(self, price: Any) -> int:
        value = Decimal(str(price))
        if not value.is_finite():
            raise ValueError("non-finite price")
        ticks = value / self.tick_size
        if ticks != ticks.to_integral_value():
            raise ValueError(f"off-grid price for {self.symbol}")
        return int(ticks)

    def price(self, ticks: int) -> Decimal:
        return Decimal(ticks) * self.tick_size

    def unit_ticks(self, units: Any) -> Decimal:
        return Decimal(str(units)) * self.distance_unit / self.tick_size


@dataclass(frozen=True)
class Bar:
    instrument: str
    tf: str
    start: datetime
    end: datetime
    open_ticks: int
    high_ticks: int
    low_ticks: int
    close_ticks: int
    available_at: datetime | None = None
    source_id: str = "declared_local_input"
    segment_id: str = "0"
    complete: bool = True
    id: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "start", utc(self.start))
        object.__setattr__(self, "end", utc(self.end))
        object.__setattr__(self, "available_at", utc(self.available_at or self.end))
        prices = (self.open_ticks, self.high_ticks, self.low_ticks, self.close_ticks)
        if any(isinstance(v, bool) or not isinstance(v, int) for v in prices):
            raise ValueError("OHLC must use integer ticks")
        if not self.low_ticks <= min(self.open_ticks, self.close_ticks) <= max(self.open_ticks, self.close_ticks) <= self.high_ticks:
            raise ValueError("invalid OHLC geometry")
        if not self.start < self.end <= self.available_at:
            raise ValueError("invalid bar interval/availability")
        object.__setattr__(self, "id", stable_id("bar", self.source_id, self.instrument, self.tf, self.start, self.end, prices))

    @property
    def clock(self) -> Clock:
        return Clock(self.start, self.end, self.available_at)

    @property
    def side(self) -> str | None:
        return "BUY" if self.close_ticks > self.open_ticks else "SELL" if self.close_ticks < self.open_ticks else None


@dataclass(frozen=True, kw_only=True)
class Event:
    id: str
    kind: str
    instrument: str
    tf: str
    clock: Clock
    side: str | None = None
    reference_id: str | None = None
    price_ticks: int | None = None
    scope_id: str | None = None
    bar_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    policy_id: str = "bishop_v2_policy_1"
    evidence_status: str = "KNOWN"
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _side(self.side)
        if hasattr(self, "price_ticks"):
            _ticks(self.price_ticks)
        object.__setattr__(self, "bar_ids", tuple(self.bar_ids))
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        object.__setattr__(self, "details", _freeze(self.details))

    @property
    def available_at(self) -> datetime:
        return self.clock.available_at


@dataclass(frozen=True, kw_only=True)
class Turn:
    id: str
    instrument: str
    tf: str
    kind: str
    price_ticks: int
    formed_at: datetime
    available_at: datetime
    anchor_bar_id: str
    confirmation_bar_id: str
    bar_ids: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _ticks(self.price_ticks)
        if self.kind not in ("H", "L"):
            raise ValueError("turn kind must be H/L")
        object.__setattr__(self, "formed_at", utc(self.formed_at))
        object.__setattr__(self, "available_at", utc(self.available_at))
        if self.available_at < self.formed_at:
            raise ValueError("turn available before formation")
        object.__setattr__(self, "bar_ids", tuple(self.bar_ids))
        object.__setattr__(self, "details", _freeze(self.details))


@dataclass(frozen=True, kw_only=True)
class Level:
    id: str
    instrument: str
    tf: str
    kind: str
    price_ticks: int
    side: str
    formed_at: datetime
    available_at: datetime
    bar_ids: tuple[str, ...] = ()
    policy_id: str = "oc_exact_junction_v1"
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _ticks(self.price_ticks)
        _side(self.side)
        if self.side is None or self.kind not in ("A", "V", "OC"):
            raise ValueError("invalid key level")
        object.__setattr__(self, "formed_at", utc(self.formed_at))
        object.__setattr__(self, "available_at", utc(self.available_at))
        if self.available_at < self.formed_at:
            raise ValueError("level available before formation")
        object.__setattr__(self, "bar_ids", tuple(self.bar_ids))
        object.__setattr__(self, "details", _freeze(self.details))

    @property
    def initial_role(self) -> str:
        return "SUPPORT" if self.side == "BUY" else "RESISTANCE"


@dataclass(frozen=True, kw_only=True)
class Liquidity:
    id: str
    instrument: str
    tf: str
    kind: str
    price_ticks: int
    formed_at: datetime
    available_at: datetime
    form: str = "BAR"
    bar_ids: tuple[str, ...] = ()
    policy_id: str = "bishop_v2_policy_1"
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _ticks(self.price_ticks)
        if self.kind not in ("HIGH", "LOW"):
            raise ValueError("liquidity kind must be HIGH/LOW")
        object.__setattr__(self, "formed_at", utc(self.formed_at))
        object.__setattr__(self, "available_at", utc(self.available_at))
        if self.available_at < self.formed_at:
            raise ValueError("liquidity available before formation")
        object.__setattr__(self, "bar_ids", tuple(self.bar_ids))
        object.__setattr__(self, "details", _freeze(self.details))


@dataclass(frozen=True, kw_only=True)
class Story:
    id: str
    instrument: str
    side: str
    origin_tf: str
    level_tf: str | None
    confirmation_tf: str
    route: str
    source_profile: str
    clock: Clock
    origin_id: str
    confirmation_id: str
    level_id: str | None = None
    parent_id: str | None = None
    scope_id: str | None = None
    destination_ticks: int | None = None
    destination_ref_id: str | None = None
    state: str = "CONFIRMED"
    evidence_ids: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _ticks(self.destination_ticks)
        _side(self.side)
        if self.side is None:
            raise ValueError("story direction required")
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        object.__setattr__(self, "details", _freeze(self.details))

    @property
    def available_at(self) -> datetime:
        return self.clock.available_at


@dataclass(frozen=True, kw_only=True)
class Setup:
    id: str
    instrument: str
    tf: str
    model: str
    side: str
    story_id: str
    clock: Clock
    entry_ticks: int
    stop_ticks: int | None
    target_ticks: int | None
    risk_profile: str
    order_type: str = "LIMIT"
    status: str = "ELIGIBLE"
    level_id: str | None = None
    liquidity_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    expires_at: datetime | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _ticks(self.entry_ticks, self.stop_ticks, self.target_ticks)
        _side(self.side)
        if self.side is None or self.order_type not in ("LIMIT", "MARKET"):
            raise ValueError("invalid setup direction/type")
        if self.status == "ELIGIBLE":
            if self.stop_ticks is None or self.target_ticks is None:
                raise ValueError("eligible setup requires risk and target")
            if not (self.stop_ticks < self.entry_ticks < self.target_ticks if self.side == "BUY" else self.target_ticks < self.entry_ticks < self.stop_ticks):
                raise ValueError("invalid directional risk geometry")
        if self.expires_at is not None:
            object.__setattr__(self, "expires_at", utc(self.expires_at))
            if self.expires_at <= self.clock.available_at:
                raise ValueError("setup expiry must follow eligibility")
        object.__setattr__(self, "liquidity_ids", tuple(self.liquidity_ids))
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        object.__setattr__(self, "details", _freeze(self.details))

    @property
    def available_at(self) -> datetime:
        return self.clock.available_at


@dataclass(frozen=True, kw_only=True)
class Order:
    id: str
    setup_id: str
    instrument: str
    tf: str
    model: str
    side: str
    kind: str
    clock: Clock
    entry_ticks: int
    stop_ticks: int
    target_ticks: int
    quantity: Decimal | str = Decimal("1")
    expires_at: datetime | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _ticks(self.entry_ticks, self.stop_ticks, self.target_ticks)
        _side(self.side)
        if self.side is None or self.kind not in ("LIMIT", "MARKET"):
            raise ValueError("invalid order direction/type")
        quantity = Decimal(str(self.quantity))
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError("positive finite quantity required")
        object.__setattr__(self, "quantity", quantity)
        if not (self.stop_ticks < self.entry_ticks < self.target_ticks if self.side == "BUY" else self.target_ticks < self.entry_ticks < self.stop_ticks):
            raise ValueError("invalid order risk geometry")
        if self.expires_at is not None:
            object.__setattr__(self, "expires_at", utc(self.expires_at))
            if self.expires_at <= self.clock.available_at:
                raise ValueError("order expiry must follow submission")
        object.__setattr__(self, "details", _freeze(self.details))

    @property
    def available_at(self) -> datetime:
        return self.clock.available_at


@dataclass(frozen=True)
class StrategyPolicy:
    version: str = "bishop_v2_policy_1"
    source_profile: str = "bishop_confirmation"
    risk_profile: str = "context_liquidity"
    target_profile: str = "nearest_erl"
    oc_gap_ticks: int = 0
    impulse_atr_fraction: Decimal | None = None
    impulse_atr_period: int = 20
    near_atr_period: int = 20
    near_atr_fraction: Decimal = Decimal("0.25")
    fixed_stop_units: Decimal = Decimal("11")
    stop_buffer_units: Decimal = Decimal("0.5")
    pending_minutes: int | None = 1440
    fallback_rejections: int = 1
    allow_counterweekly: bool = True
    entry_tfs: tuple[str, ...] = ("H4", "H3", "H2", "H1", "M45", "M30", "M15", "M5")
    origin_tfs: tuple[str, ...] = ("M", "W", "D", "H4")
    id: str = field(init=False)

    def __post_init__(self):
        allowed = {
            "source_profile": {"bishop_confirmation", "source_all", "all_routes", "owner_aggressive", "aggressive_direct", "plug_and_play", "core_course", "nested_confirmation"},
            "risk_profile": {"context_liquidity", "source_structural", "structural", "owner_fixed11", "fixed11", "fixed", "fixed_pips", "zone_edge"},
            "target_profile": {"nearest_erl", "entry_erl", "fixed3r", "fixed_r", "story_destination"},
        }
        for name, choices in allowed.items():
            if getattr(self, name) not in choices:
                raise ValueError(f"unknown {name}")
        for name in ("oc_gap_ticks", "near_atr_period", "fallback_rejections", "impulse_atr_period"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"integer {name} required")
        if self.pending_minutes is not None and type(self.pending_minutes) is not int:
            raise ValueError("integer pending_minutes required")
        if type(self.allow_counterweekly) is not bool:
            raise ValueError("boolean allow_counterweekly required")
        for name in ("entry_tfs", "origin_tfs"):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or not values or len(set(values)) != len(values):
                raise ValueError(f"nonempty unique {name} required")
            for tf in values:
                if not isinstance(tf, str) or not (tf in ("D", "W", "M", "MN1") or (tf[:1] in ("H", "M") and tf[1:].isdigit() and int(tf[1:]) > 0)):
                    raise ValueError(f"invalid timeframe {tf}")
        if self.impulse_atr_fraction is not None:
            value = Decimal(str(self.impulse_atr_fraction))
            if not value.is_finite() or value <= 0:
                raise ValueError("positive impulse_atr_fraction required")
            object.__setattr__(self, "impulse_atr_fraction", value)
        if self.impulse_atr_period < 1:
            raise ValueError("positive impulse_atr_period required")
        for name in ("near_atr_fraction", "fixed_stop_units", "stop_buffer_units"):
            value = Decimal(str(getattr(self, name)))
            if not value.is_finite() or value < 0:
                raise ValueError(f"invalid {name}")
            object.__setattr__(self, name, value)
        if self.oc_gap_ticks < 0 or self.near_atr_period < 1 or self.fallback_rejections < 1:
            raise ValueError("invalid numerical policy")
        if self.fixed_stop_units <= 0 or (self.pending_minutes is not None and self.pending_minutes <= 0):
            raise ValueError("invalid risk/expiry policy")
        object.__setattr__(self, "entry_tfs", tuple(self.entry_tfs))
        object.__setattr__(self, "origin_tfs", tuple(self.origin_tfs))
        object.__setattr__(self, "id", stable_id("policy", {f.name: getattr(self, f.name) for f in fields(self) if f.init}))
