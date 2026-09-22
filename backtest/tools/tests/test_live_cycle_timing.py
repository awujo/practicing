import json

import pytest

from ..live_cycle_timing import CONFIGS, CYCLE_BUDGET_S, STALE_CUTOFF_S, load_windows
from ..slk_system import SLK_OPERATIONAL, slk_kwargs


def test_windows_use_the_live_resolver_not_a_reimplementation():
    """An explicit null in history_windows.json means "confirmed NOT safe
    to cap" -- GBPNZD never converged even at a 15-year ceiling -- which
    is deliberately different from "absent, use the default".

    A `per.get(inst, default)` reimplementation agrees with that by
    accident of Python semantics, not by construction. Agreeing by luck
    is not agreeing, so the real resolver is called."""
    import inspect

    from ..live_cycle_timing import load_windows as lw
    assert "resolve_history_window_years" in inspect.getsource(lw)

    window_for = load_windows(instruments=("EURUSD", "GBPNZD", "USOIL"))
    assert window_for("EURUSD")["H1"] >= 1
    # Explicit null -> uncapped, i.e. absent from the resolved mapping.
    assert window_for("GBPNZD") is None
    # Absent from the file -> the default applies.
    assert window_for("USOIL") is not None


def test_it_can_time_both_the_shipped_and_the_slk_configuration():
    """Without a baseline, a number is not a verdict -- "40 minutes" only
    means something next to what the bots do today."""
    assert set(CONFIGS) == {"shipped", "slk"}
    shipped = CONFIGS["shipped"]()
    slk = CONFIGS["slk"]()
    # Shipped is the operational settings only: no taught rules.
    assert shipped == dict(SLK_OPERATIONAL)
    assert "confirmation_triggers" not in shipped
    assert slk == slk_kwargs()
    assert slk["confirmation_triggers"] != ()


def test_the_budgets_are_the_bots_own_numbers():
    """3600s is one H1 candle; 3h is STALE_ENTRY_CUTOFF. Hardcoding a
    round number instead would report against a bar nobody enforces."""
    from ...  import __name__ as _  # noqa: F401  (package import sanity)
    import importlib

    orchestrator = importlib.import_module("bot.orchestrator")
    assert STALE_CUTOFF_S == orchestrator.STALE_ENTRY_CUTOFF.total_seconds()
    assert CYCLE_BUDGET_S == 3600.0


def test_a_malformed_windows_file_fails_loudly(tmp_path):
    p = tmp_path / "w.json"
    p.write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        load_windows(str(p))
