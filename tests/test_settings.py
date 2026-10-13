"""Strategy settings: schema validation, cfg building for the live runner, story break kinds (external only)."""
import subprocess
import sys

import pandas as pd
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
    assert "confirm_break" not in vals and vals["continuation_entries"] is True
    assert {s["group"] for s in S.SCHEMA} == set(S.GROUPS) and all(s["help"] for s in S.SCHEMA)


@pytest.mark.parametrize("k,v,want", [
    ("max_wait", "7", "7"), ("max_wait", 20, "20"), ("tap_tol_pips", 0.5, "0.5"), ("risk_pct", "2", "2"),
    ("trend_filter", True, "on"), ("htf_filter", "false", "off"),
    ("stories", "m, d", "D,M"), ("pairs", "eurusd gbpjpy,EURUSD", "EURUSD,GBPJPY"), ("avoid_pairs", "", ""),
    ("entry_tfs", "D=H4,H1; W:D", "D=H4,H1;W=D;M=W,D"), ("auto_trade", "confirm", "confirm"),
])
def test_clean_ok(k, v, want):
    assert S.clean(k, v) == want


@pytest.mark.parametrize("k,v", [
    ("max_wait", 0), ("max_wait", 21), ("max_wait", "2.5"), ("max_retaps", 11), ("tap_tol_pips", 6),
    ("max_stop_pips", 4), ("risk_pct", 0.05), ("risk_pct", 3), ("trend_filter", "maybe"),
    ("confirm_break", "external"), ("confirm_break", "internal"), ("stories", "D,H4"), ("stories", ""), ("pairs", "EUR/USD"), ("entry_tfs", "D=W"),
    ("entry_tfs", "X=H1"), ("kill_switch", "yes please"), ("nope", 1), ("max_wait", True),
])
def test_clean_bad(k, v):
    with pytest.raises(ValueError):
        S.clean(k, v)


def test_build_cfg_from_stored_strings():
    stored = {"confirm_break": "internal", "trend_filter": "off", "max_wait": "9", "tap_tol_pips": "2.5",
              "entry_tfs": "D=H1;W=H4;M=D", "max_stop_pips": "30", "tp1_rr": "2", "avoid_pairs": "",
              "skip_first_retracement": "off", "max_retaps": "junk", "alert_tapped": "off"}
    cfg, ecfg, vals = build_cfg(stored, {"max_hold": 7})
    assert "confirm_break" not in cfg and cfg["trend_filter"] is False and cfg["max_wait"] == 9
    assert cfg["tap_tol_pips"] == 2.5 and cfg["max_hold"] == 7
    assert cfg["max_retaps"] == story.DEFAULT["max_retaps"]  # bad stored value -> code default
    assert ecfg["entry_tfs"] == {"D": ("H1",), "W": ("H4",), "M": ("D",)} and ecfg["avoid_pairs"] == []
    assert ecfg["max_stop_pips"] == 30 and ecfg["tp1_min_rr"] == 2 and ecfg["skip_first"] is False
    assert ecfg["retest_bars"] == entry.DEFAULT["retest_bars"]
    al = [("TAPPED", {}), ("CONFIRMED", {}), ("INVALIDATED", {})]
    assert [e for e, _ in alerts_enabled(al, vals)] == ["CONFIRMED", "INVALIDATED"]
    cfg0, ecfg0, _ = build_cfg({})
    assert cfg0 == story.DEFAULT and ecfg0["entry_tfs"] == entry.ENTRY_TFS


def test_break_is_always_external():
    """Kevin: "sweep and break" OR "breakout" [T story-line-pt2@297-441]; both are a confirm-TF body close beyond
    point B (last swing before the first tap). The sweep is only a label; no cfg relaxes the break."""
    h1 = walk()
    rows = story.find_stories("EURUSD", h1, "D")
    assert rows and {r["break_kind"] for r in rows} <= {"breakout", "sweep_break"}
    assert story.find_stories("EURUSD", h1, "D", {"confirm_break": "external_or_sweep"}) == rows  # ignored
    h4, d = resample(h1, "H4"), resample(h1, "D")
    close4 = dict(zip(h4["start"].astype(str).str[:16], h4["close"]))
    for r in rows:
        c = close4[r["breakout_time"]]
        assert (c < r["B"]) if r["side"] == "SELL" else (c > r["B"])
        # same_bar_close: the daily bar holding the breakout closes beyond B too
        dbar = d[pd.to_datetime(d["start"]).dt.tz_localize(None) <= pd.Timestamp(r["breakout_time"])].iloc[-1]
        assert (dbar["close"] < r["B"]) if r["side"] == "SELL" else (dbar["close"] > r["B"])


def test_break_kind_label():
    import numpy as np
    C = {"high": np.array([1.0, 1.2, 1.1, 1.25, 1.0]), "low": np.array([0.9] * 5),
         "close": np.array([0.95, 1.1, 1.0, 1.15, 0.8])}
    sw = [(1, "H", 1.1, 3)]
    assert story._break_kind(True, sw, 3, 4, C) == "sweep_break"  # wick 1.25 > high 1.2, close 1.15 back below
    C["close"][3] = 1.21
    assert story._break_kind(True, sw, 3, 4, C) == "breakout"     # closed beyond: not a sweep
    assert story._break_kind(True, [], 3, 4, C) == "breakout"


def test_mw_check_runs_even_when_only_d_is_watched():
    from slk.live import state_stories
    assert state_stories(["D"], {}) == ["D", "W", "M"]
    assert state_stories(["D", "M"], {}) == ["D", "M", "W"]
    assert state_stories(["D"], {"mw_conflict_filter": False}) == ["D"]
    assert state_stories(["W"], {}) == ["W"]
