"""Tests for run_live.py's resolve_history_window_years() -- the pure
function that turns a --history-windows-config file's two-tier
{default, instruments} structure into the flat dict LiveBot wants.
"""

from ..run_live import resolve_history_window_years

DEFAULT = {"D": 2, "W": 2, "H4": 1, "H1": 1}
EURUSD_WINDOW = {"D": 8, "W": 8, "H4": 4, "H1": 4}


def test_an_instrument_with_a_specific_override_uses_it_not_the_default():
    config = {"default": DEFAULT, "instruments": {"EURUSD": EURUSD_WINDOW}}
    resolved = resolve_history_window_years(config, ("EURUSD",))
    assert resolved == {"EURUSD": EURUSD_WINDOW}


def test_an_instrument_with_no_entry_falls_back_to_the_default():
    config = {"default": DEFAULT, "instruments": {"EURUSD": EURUSD_WINDOW}}
    resolved = resolve_history_window_years(config, ("EURUSD", "GBPCHF"))
    assert resolved == {"EURUSD": EURUSD_WINDOW, "GBPCHF": DEFAULT}


def test_an_explicit_null_override_stays_uncapped_even_with_a_default_set():
    """The whole point of an explicit null (e.g. GBPNZD): it must NOT
    silently inherit the flat default just because one is configured."""
    config = {"default": DEFAULT, "instruments": {"GBPNZD": None}}
    resolved = resolve_history_window_years(config, ("GBPNZD",))
    assert resolved == {}


def test_no_default_configured_means_unlisted_instruments_stay_uncapped():
    config = {"default": None, "instruments": {"EURUSD": EURUSD_WINDOW}}
    resolved = resolve_history_window_years(config, ("EURUSD", "GBPCHF"))
    assert resolved == {"EURUSD": EURUSD_WINDOW}


def test_missing_instruments_section_treated_as_empty():
    config = {"default": DEFAULT}
    resolved = resolve_history_window_years(config, ("EURUSD",))
    assert resolved == {"EURUSD": DEFAULT}


def test_only_instruments_actually_being_run_are_resolved():
    """An instrument configured in the file but not part of THIS run's
    --instruments list must not appear in the result."""
    config = {"default": DEFAULT, "instruments": {"EURUSD": EURUSD_WINDOW, "GBPJPY": EURUSD_WINDOW}}
    resolved = resolve_history_window_years(config, ("EURUSD",))
    assert resolved == {"EURUSD": EURUSD_WINDOW}


# ---------------------------------------------------------------------------
# Bias-flip state-machine CLI flags (2026-09-30 wiring)
#
# main() cannot be invoked directly in a test (it connects to MT5), so the
# parser is rebuilt here by extracting and exec-ing only the argparse block
# from run_live.py's source. If that block ever stops starting with the
# ArgumentParser construction or the orchestrator call stops sitting at the
# end of main(), these tests fail loudly rather than silently testing
# nothing -- which is exactly the gate-vs-engine drift class they guard.
# ---------------------------------------------------------------------------

import argparse
import ast
import os
import textwrap

import pytest


def _main_source_lines():
    """(source text, statements of main()) for bot/run_live.py."""
    import bot.run_live as rl
    src = open(rl.__file__).read()
    tree = ast.parse(src)
    main_fn = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "main")
    return src, main_fn.body


def _build_argparser():
    src, stmts = _main_source_lines()
    start = next(i for i, s in enumerate(stmts)
                 if "ArgumentParser" in ast.dump(s))
    end = next(i for i, s in enumerate(stmts)
               if isinstance(s, ast.Assign)
               and getattr(s.targets[0], "id", "") == "bot")
    first_line = stmts[start].lineno
    last_line = stmts[end - 1].end_lineno
    block_src = "\n".join(src.splitlines()[first_line - 1:last_line])
    # The argparse block sits inside main(), whose surrounding code uses
    # module-level imports (os.path for default audit-db paths, etc.).
    # exec() needs those names in its namespace or the parser's own
    # defaults blow up with NameError. Seed it with run_live's own module
    # globals so any name the block references resolves exactly as it
    # does at runtime.
    #
    # It also contains `args = parser.parse_args()` -- with no argv, that
    # would parse PYTEST's own command line and abort the fixture with
    # SystemExit(2). Stub parse_args to return None; we only want the
    # finished parser object off the namespace.
    import bot.run_live as rl
    ns = dict(vars(rl))
    ns["argparse"] = argparse
    ns["os"] = os
    real_parse_args = argparse.ArgumentParser.parse_args

    def _stubbed_parse_args(self, args=None, namespace=None):
        return None

    argparse.ArgumentParser.parse_args = _stubbed_parse_args
    try:
        exec(textwrap.dedent(block_src), ns)
    finally:
        argparse.ArgumentParser.parse_args = real_parse_args
    return ns["parser"]


@pytest.fixture(scope="module")
def argparser():
    return _build_argparser()


BASE_ARGV = ["--account-type", "personal", "--instruments", "EURUSD"]


def test_flip_flags_default_to_off(argparser):
    """Both guards OFF by default: every recorded number reproduces."""
    args = argparser.parse_args(BASE_ARGV)
    assert args.require_flip_confirmation is False
    assert args.require_flip_touch is False


def test_flip_flags_parse_as_store_true(argparser):
    args = argparser.parse_args(
        BASE_ARGV + ["--require-flip-confirmation", "--require-flip-touch"])
    assert args.require_flip_confirmation is True
    assert args.require_flip_touch is True


def test_flip_flags_are_independent(argparser):
    """Wiring one without the other is legal (they guard different flip
    conditions) and must not cross-set each other."""
    only_conf = argparser.parse_args(BASE_ARGV + ["--require-flip-confirmation"])
    assert only_conf.require_flip_confirmation is True
    assert only_conf.require_flip_touch is False
    only_touch = argparser.parse_args(BASE_ARGV + ["--require-flip-touch"])
    assert only_touch.require_flip_confirmation is False
    assert only_touch.require_flip_touch is True


def test_main_passes_both_flip_flags_to_the_orchestrator():
    """The exact drift bug this guards: flags exist on the parser but are
    dropped between parse_args() and LiveBot(...). Assert both names
    appear as keyword arguments in main()'s `bot = LiveBot(...)` call."""
    _, stmts = _main_source_lines()
    assign = next(s for s in stmts
                  if isinstance(s, ast.Assign)
                  and getattr(s.targets[0], "id", "") == "bot")
    assert isinstance(assign.value, ast.Call)
    assert getattr(assign.value.func, "id", "") == "LiveBot"
    kwargs = {kw.arg for kw in assign.value.keywords}
    assert {"require_flip_confirmation", "require_flip_touch"} <= kwargs
    for kw in assign.value.keywords:
        if kw.arg in ("require_flip_confirmation", "require_flip_touch"):
            assert isinstance(kw.value, ast.Attribute)
            assert kw.value.value.id == "args"
