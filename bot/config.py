"""
Account/phase configuration for the live trading bot.

Two account types, selected explicitly (never inferred):

  - "prop_firm": has phases (phase1 -> phase2 -> funded), each with its
    OWN MT5 login (real prop firms issue a fresh account per phase) and
    its OWN rule set (profit target, daily/overall drawdown limits, risk
    per trade, the de-risk threshold). Selecting a phase swaps the MT5
    connection and the active rule set together, atomically -- there is
    no way to end up trading Phase 2 risk rules against a Phase 1 login,
    or vice versa, because both live on the same PhaseConfig object.
  - "personal": a single MT5 login, a flat risk-per-trade, and no
    drawdown-triggered termination (matches simulate.py's PersonalSim
    from the offline analysis this is built on).

Credentials are NEVER read from a committed file. They come from
environment variables only, following the same pattern as
backtest/webapp/app.py's WEBAPP_USERNAME/WEBAPP_PASSWORD and
backtest/webapp/data_access.py's GITHUB_TOKEN -- see `_credentials_from_env()`.
The rule sets (targets, DD limits, risk amounts) are NOT secret and can
live in a committed profile file; only login/password/server are secret.
"""

import os
from dataclasses import dataclass, field

PROP_FIRM_PHASES = ("phase1", "phase2", "funded")


@dataclass(frozen=True)
class MT5Credentials:
    login: int
    password: str
    server: str


@dataclass(frozen=True)
class SymbolMap:
    """How internal instrument codes (backtest/data_pipeline/instruments.py's
    EURUSD, NAS100, JP225, ...) map onto whatever a specific broker's
    Market Watch actually calls them. A single suffix (".a", "m", ...)
    covers most brokers, but NOT all -- confirmed on MetaQuotes-Demo, for
    example: `NAS100` doesn't exist at all, it's `USTEC`; `JP225` is
    `JPN225`. `overrides` handles a genuine rename like that; `suffix`
    still applies to every OTHER symbol not explicitly overridden."""
    suffix: str = ""
    overrides: dict[str, str] = field(default_factory=dict)

    def broker_symbol(self, internal_symbol: str) -> str:
        if internal_symbol in self.overrides:
            return self.overrides[internal_symbol]
        return f"{internal_symbol}{self.suffix}"

    def internal_symbol(self, broker_symbol: str) -> str:
        """The reverse mapping, for reading MT5 back.

        Positions and orders come back from MT5 labelled with the BROKER's
        name, while the rest of this codebase thinks in internal codes, so
        anything matching them up needs this direction too. An override
        wins over the suffix rule (USTEC is not "USTEC" minus a suffix),
        and an unrecognised name is returned unchanged rather than
        mangled -- a symbol we don't manage should stay identifiable in
        logs, not silently become something else."""
        for internal, broker in self.overrides.items():
            if broker == broker_symbol:
                return internal
        if self.suffix and broker_symbol.endswith(self.suffix):
            return broker_symbol[: -len(self.suffix)]
        return broker_symbol


@dataclass(frozen=True)
class PhaseRules:
    """The risk rules active for one phase. `profit_target_pct=None` means
    no target (funded stage: no target to hit, just don't breach)."""
    daily_dd_limit_pct: float
    overall_dd_limit_pct: float
    risk_normal: float
    risk_reduced: float
    de_risk_at_pct: float          # switch to risk_reduced once overall DD reaches this
    profit_target_pct: float | None = None
    admin_gap_days: int = 2        # no trading between hitting target and the next phase's login arriving


@dataclass(frozen=True)
class PhaseConfig:
    rules: PhaseRules
    credentials: MT5Credentials
    starting_balance: float = 100000.0


@dataclass(frozen=True)
class PersonalRules:
    risk_flat: float


@dataclass
class AccountProfile:
    """The single object that fully determines "which rules apply right
    now" -- constructed once at startup (or on an explicit phase change),
    never mutated implicitly. Changing phase means constructing a NEW
    AccountProfile, so there's no window where risk_manager code could
    read a stale phase's rules against a freshly-swapped MT5 connection."""
    account_type: str  # "prop_firm" | "personal"
    active_phase: str | None = None            # prop_firm only
    phases: dict[str, PhaseConfig] = field(default_factory=dict)  # prop_firm only
    personal: PersonalRules | None = None
    personal_credentials: MT5Credentials | None = None

    def __post_init__(self):
        if self.account_type not in ("prop_firm", "personal"):
            raise ValueError(f"account_type must be 'prop_firm' or 'personal', got {self.account_type!r}")
        if self.account_type == "prop_firm":
            if self.active_phase not in PROP_FIRM_PHASES:
                raise ValueError(f"active_phase must be one of {PROP_FIRM_PHASES}, got {self.active_phase!r}")
            if self.active_phase not in self.phases:
                raise ValueError(f"no PhaseConfig registered for active_phase {self.active_phase!r}")
        else:
            if self.personal is None or self.personal_credentials is None:
                raise ValueError("personal account_type requires both `personal` rules and `personal_credentials`")

    @property
    def active_credentials(self) -> MT5Credentials:
        if self.account_type == "prop_firm":
            return self.phases[self.active_phase].credentials
        return self.personal_credentials

    @property
    def active_rules(self) -> PhaseRules:
        """Always returns a PhaseRules, even for a personal account, so
        risk_manager.py has exactly one shape to work with -- a personal
        account's PhaseRules just has no target and no DD-triggered
        termination (see `RiskManager` for how that's honored)."""
        if self.account_type == "prop_firm":
            return self.phases[self.active_phase].rules
        return PhaseRules(
            daily_dd_limit_pct=1.0,       # effectively "no limit" -- see RiskManager.terminates_on_dd
            overall_dd_limit_pct=1.0,
            risk_normal=self.personal.risk_flat,
            risk_reduced=self.personal.risk_flat,
            de_risk_at_pct=1.0,
            profit_target_pct=None,
        )

    @property
    def terminates_on_dd(self) -> bool:
        return self.account_type == "prop_firm"

    @property
    def starting_balance(self) -> float:
        if self.account_type == "prop_firm":
            return self.phases[self.active_phase].starting_balance
        return 100000.0


def _credentials_from_env(prefix: str) -> MT5Credentials:
    """Reads {PREFIX}_LOGIN / {PREFIX}_PASSWORD / {PREFIX}_SERVER from the
    environment. Raises loudly (not a silent None) if any piece is
    missing -- a half-configured account must never silently fall back to
    trading on the wrong login."""
    login = os.environ.get(f"{prefix}_LOGIN")
    password = os.environ.get(f"{prefix}_PASSWORD")
    server = os.environ.get(f"{prefix}_SERVER")
    missing = [name for name, val in (("LOGIN", login), ("PASSWORD", password), ("SERVER", server)) if not val]
    if missing:
        raise RuntimeError(f"{prefix}_* is missing {missing} -- set all three env vars before starting the bot.")
    return MT5Credentials(login=int(login), password=password, server=server)


# Default prop-firm rule sets, matching the numbers this whole analysis was
# built on (see bot/README.md / the offline simulate_v2_safe.py it's ported
# from). Override per-firm by constructing PhaseRules directly if a
# different prop firm uses different numbers.
DEFAULT_PHASE1_RULES = PhaseRules(
    daily_dd_limit_pct=0.04, overall_dd_limit_pct=0.10,
    risk_normal=1000.0, risk_reduced=500.0, de_risk_at_pct=0.05,
    profit_target_pct=0.08,
)
DEFAULT_PHASE2_RULES = PhaseRules(
    daily_dd_limit_pct=0.04, overall_dd_limit_pct=0.10,
    risk_normal=1000.0, risk_reduced=500.0, de_risk_at_pct=0.05,
    profit_target_pct=0.04,
)
DEFAULT_FUNDED_RULES = PhaseRules(
    daily_dd_limit_pct=0.04, overall_dd_limit_pct=0.10,
    risk_normal=1000.0, risk_reduced=500.0, de_risk_at_pct=0.05,
    profit_target_pct=None,
)


def load_prop_firm_profile(active_phase: str) -> AccountProfile:
    """Builds a prop-firm AccountProfile with the default rule sets,
    reading each phase's MT5 credentials from MT5_PHASE1_*, MT5_PHASE2_*,
    MT5_FUNDED_* env vars. Only the `active_phase`'s credentials are
    required to be present -- you won't have Phase 2's login yet while
    still trading Phase 1."""
    rules_by_phase = {"phase1": DEFAULT_PHASE1_RULES, "phase2": DEFAULT_PHASE2_RULES, "funded": DEFAULT_FUNDED_RULES}
    creds = _credentials_from_env(f"MT5_{active_phase.upper()}")
    phases = {active_phase: PhaseConfig(rules=rules_by_phase[active_phase], credentials=creds)}
    return AccountProfile(account_type="prop_firm", active_phase=active_phase, phases=phases)


def load_personal_profile(risk_flat: float = 1000.0) -> AccountProfile:
    creds = _credentials_from_env("MT5_PERSONAL")
    return AccountProfile(account_type="personal",
                           personal=PersonalRules(risk_flat=risk_flat),
                           personal_credentials=creds)
