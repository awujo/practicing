"""Strategy settings: schema validation, cfg building for the live runner, story confirm_break variants."""
import subprocess
import sys

import pytest

from slk.candles import resample
from slk import entry, settings as S, story
from slk.live import alerts_enabled, build_cfg
from test_engine import walk


def test_settings_module_has_no_pandas():
    code = "import sys; import slk.settings; assert 'pandas' not in sys.modules and 'numpy' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_defaults_match_code_defaults():
    vals = S.load({})
    for k, v in S.story_cfg(vals).items():
        assert story.DEFAULT[k] == v, k
    e = S.entry_cfg(vals)
    assert e["entry_tfs"] == entry.ENTRY_TFS
    assert e["max_stop_pips"] == entry.DEFAULT["max_stop_pips"] and e["tp1_min_rr"] == entry.DEFAULT["tp1_min_rr"]
    assert e["avoid_pairs"] == entry.DEFAULT["avoid_pairs"] and e["skip_first"] == entry.DEFAULT["skip_first"]
    assert vals["confirm_break"] == "external" and vals["continuation_entries"] is True
    assert {s["group"] for s in S.SCHEMA} == set(S.GROUPS) and all(s["help"] for s in S.SCHEMA)


@pytest.mark.parametrize("k,v,want", [
    ("max_wait", "7", "7"), ("max_wait", 20, "20"), ("tap_tol_pips", 0.5, "0.5"), ("risk_pct", "2", "2"),
    ("trend_filter", True, "on"), ("htf_filter", "false", "off"), ("confirm_break", "External_or_sweep",
                                                                    "external_or_sweep"),
    ("stories", "m, d", "D,M"), ("pairs", "eurusd gbpjpy,EURUSD", "EURUSD,GBPJPY"), ("avoid_pairs", "", ""),
    ("entry_tfs", "D=H4,H1; W:D", "D=H4,H1;W=D;M=W,D"), ("auto_trade", "confirm", "confirm"),
])
def test_clean_ok(k, v, want):
    assert S.clean(k, v) == want


@pytest.mark.parametrize("k,v", [
    ("max_wait", 0), ("max_wait", 21), ("max_wait", "2.5"), ("max_retaps", 11), ("tap_tol_pips", 6),
    ("max_stop_pips", 4), ("risk_pct", 0.05), ("risk_pct", 3), ("trend_filter", "maybe"),
    ("confirm_break", "internal"), ("stories", "D,H4"), ("pairs", "EUR/USD"), ("entry_tfs", "D=W"),
    ("entry_tfs", "X=H1"), ("kill_switch", "yes please"), ("nope", 1), ("max_wait", True),
])
def test_clean_bad(k, v):
    with pytest.raises(ValueError):
        S.clean(k, v)


def test_build_cfg_from_stored_strings():
    stored = {"confirm_break": "external_or_sweep", "trend_filter": "off", "max_wait": "9", "tap_tol_pips": "2.5",
              "entry_tfs": "D=H1;W=H4;M=D", "max_stop_pips": "30", "tp1_rr": "2", "avoid_pairs": "",
              "skip_first_retracement": "off", "max_retaps": "junk", "alert_tapped": "off"}
    cfg, ecfg, vals = build_cfg(stored, {"max_hold": 7})
    assert cfg["confirm_break"] == "external_or_sweep" and cfg["trend_filter"] is False and cfg["max_wait"] == 9
    assert cfg["tap_tol_pips"] == 2.5 and cfg["max_hold"] == 7
    assert cfg["max_retaps"] == story.DEFAULT["max_retaps"]  # bad stored value -> code default
    assert ecfg["entry_tfs"] == {"D": ("H1",), "W": ("H4",), "M": ("D",)} and ecfg["avoid_pairs"] == []
    assert ecfg["max_stop_pips"] == 30 and ecfg["tp1_min_rr"] == 2 and ecfg["skip_first"] is False
    assert ecfg["retest_bars"] == entry.DEFAULT["retest_bars"]
    al = [("TAPPED", {}), ("CONFIRMED", {}), ("INVALIDATED", {})]
    assert [e for e, _ in alerts_enabled(al, vals)] == ["CONFIRMED", "INVALIDATED"]
    cfg0, ecfg0, _ = build_cfg({})
    assert cfg0 == story.DEFAULT and ecfg0["entry_tfs"] == entry.ENTRY_TFS


def test_confirm_break_external_is_unchanged_default():
    h1 = walk()
    a = story.find_stories("EURUSD", h1, "D")
    b = story.find_stories("EURUSD", h1, "D", {"confirm_break": "external"})
    assert a == b and a and all(r["break_kind"] == "external" for r in a)


def test_confirm_break_external_or_sweep():
    h1 = walk()
    ext = story.find_stories("EURUSD", h1, "D")
    sw = story.find_stories("EURUSD", h1, "D", {"confirm_break": "external_or_sweep"})
    kinds = {r["break_kind"] for r in sw}
    assert kinds <= {"external", "sweep"} and "sweep" in kinds
    assert {r["tap_time"] for r in ext} <= {r["tap_time"] for r in sw}  # adds sweep+break stories
    h4 = resample(h1, "H4")
    close_at = dict(zip(h4["start"].astype(str).str[:16], h4["close"]))
    for r in sw:  # the breakout still is an H4 body close beyond B (external break), never an internal one
        c = close_at[r["breakout_time"]]
        assert (c < r["B"]) if r["side"] == "SELL" else (c > r["B"])
    for st in ("D", "W"):
        story.current_tap("EURUSD", h1, st, {"confirm_break": "external_or_sweep"})


def test_confirm_break_rejects_internal():
    with pytest.raises(ValueError):
        story.find_stories("EURUSD", walk(24 * 60), "D", {"confirm_break": "internal"})
