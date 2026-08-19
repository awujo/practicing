import pytest

from ..config import (
    AccountProfile, MT5Credentials, PhaseConfig, PhaseRules, PersonalRules, SymbolMap,
    DEFAULT_PHASE1_RULES, DEFAULT_PHASE2_RULES, DEFAULT_FUNDED_RULES,
    _credentials_from_env, load_prop_firm_profile, load_personal_profile,
)

CREDS = MT5Credentials(login=12345, password="hunter2", server="PropFirmX-Live")


def _phase1_profile(active="phase1"):
    return AccountProfile(
        account_type="prop_firm",
        active_phase=active,
        phases={
            "phase1": PhaseConfig(rules=DEFAULT_PHASE1_RULES, credentials=CREDS),
            "phase2": PhaseConfig(rules=DEFAULT_PHASE2_RULES,
                                   credentials=MT5Credentials(99999, "pw2", "PropFirmX-Live")),
        },
    )


def test_prop_firm_profile_exposes_the_active_phases_rules_and_credentials():
    profile = _phase1_profile()
    assert profile.active_rules is DEFAULT_PHASE1_RULES
    assert profile.active_credentials == CREDS
    assert profile.terminates_on_dd is True


def test_switching_active_phase_switches_both_rules_and_credentials_atomically():
    profile = _phase1_profile(active="phase2")
    assert profile.active_rules is DEFAULT_PHASE2_RULES
    assert profile.active_credentials.login == 99999


def test_prop_firm_profile_rejects_an_unregistered_active_phase():
    with pytest.raises(ValueError):
        AccountProfile(account_type="prop_firm", active_phase="funded", phases={})


def test_prop_firm_profile_rejects_an_unknown_phase_name():
    with pytest.raises(ValueError):
        AccountProfile(account_type="prop_firm", active_phase="phase99", phases={})


def test_account_type_must_be_prop_firm_or_personal():
    with pytest.raises(ValueError):
        AccountProfile(account_type="nonsense")


def test_personal_profile_requires_rules_and_credentials():
    with pytest.raises(ValueError):
        AccountProfile(account_type="personal")


def test_personal_profile_has_flat_risk_and_never_terminates_on_dd():
    profile = AccountProfile(account_type="personal",
                              personal=PersonalRules(risk_flat=1000.0),
                              personal_credentials=CREDS)
    assert profile.active_rules.risk_normal == 1000.0
    assert profile.active_rules.risk_reduced == 1000.0
    assert profile.active_rules.profit_target_pct is None
    assert profile.terminates_on_dd is False
    assert profile.active_credentials == CREDS


def test_credentials_from_env_reads_all_three_fields(monkeypatch):
    monkeypatch.setenv("MT5_PHASE1_LOGIN", "555")
    monkeypatch.setenv("MT5_PHASE1_PASSWORD", "secret")
    monkeypatch.setenv("MT5_PHASE1_SERVER", "SomeServer-Demo")
    creds = _credentials_from_env("MT5_PHASE1")
    assert creds == MT5Credentials(login=555, password="secret", server="SomeServer-Demo")


def test_credentials_from_env_raises_loudly_on_partial_config(monkeypatch):
    monkeypatch.delenv("MT5_PHASE1_LOGIN", raising=False)
    monkeypatch.setenv("MT5_PHASE1_PASSWORD", "secret")
    monkeypatch.delenv("MT5_PHASE1_SERVER", raising=False)
    with pytest.raises(RuntimeError, match="LOGIN"):
        _credentials_from_env("MT5_PHASE1")


def test_load_prop_firm_profile_only_requires_the_active_phases_credentials(monkeypatch):
    monkeypatch.setenv("MT5_PHASE1_LOGIN", "1")
    monkeypatch.setenv("MT5_PHASE1_PASSWORD", "pw")
    monkeypatch.setenv("MT5_PHASE1_SERVER", "Srv")
    monkeypatch.delenv("MT5_PHASE2_LOGIN", raising=False)
    profile = load_prop_firm_profile("phase1")
    assert profile.active_phase == "phase1"
    assert profile.active_rules.profit_target_pct == 0.08


def test_load_personal_profile_reads_mt5_personal_env_vars(monkeypatch):
    monkeypatch.setenv("MT5_PERSONAL_LOGIN", "42")
    monkeypatch.setenv("MT5_PERSONAL_PASSWORD", "pw")
    monkeypatch.setenv("MT5_PERSONAL_SERVER", "Srv")
    profile = load_personal_profile(risk_flat=750.0)
    assert profile.account_type == "personal"
    assert profile.active_rules.risk_normal == 750.0


# ---- SymbolMap ----

def test_symbol_map_applies_the_suffix_to_unmapped_symbols():
    m = SymbolMap(suffix=".a")
    assert m.broker_symbol("EURUSD") == "EURUSD.a"


def test_symbol_map_with_no_suffix_returns_the_plain_name():
    m = SymbolMap()
    assert m.broker_symbol("EURUSD") == "EURUSD"


def test_symbol_map_override_takes_priority_over_the_suffix():
    # Confirmed on MetaQuotes-Demo: NAS100 doesn't exist as such -- it's
    # USTEC. A suffix alone can never produce that, only an override can.
    m = SymbolMap(suffix=".a", overrides={"NAS100": "USTEC", "JP225": "JPN225"})
    assert m.broker_symbol("NAS100") == "USTEC"
    assert m.broker_symbol("JP225") == "JPN225"
    assert m.broker_symbol("EURUSD") == "EURUSD.a"  # unmapped symbols still get the suffix
