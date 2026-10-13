"""Regression tests for the fixes listed in REVIEW.md (no network, no DB)."""
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from slk import data
from slk.candles import resample
from slk.entry import find_entries
from slk.story import DEFAULT, STORIES, current_tap, find_stories
from tests.test_engine import walk
from tests.test_entry import H1ONLY, scenario, story_row

ROOT = Path(__file__).resolve().parents[1]


def _ts(s):
    return pd.Timestamp(s, tz="UTC")


def test_confirmation_waits_for_origin_close_used_by_same_bar_close():
    """same_bar_close reads the close of the origin bar holding the breakout, so the story can only be
    confirmed once that bar has closed (no look-ahead)."""
    h1 = walk()
    n = 0
    for st in ("D", "W"):
        ob = resample(h1, STORIES[st][0])
        for r in find_stories("EURUSD", h1, st):
            k = int((ob["start"] <= _ts(r["breakout_time"])).sum()) - 1
            assert _ts(r["confirm_time"]) >= ob["end"].iat[k]
            n += 1
    assert n > 0


def test_htf_filter_never_against_higher_tf_trend():
    h1 = walk()
    rows = find_stories("EURUSD", h1, "D")
    assert rows
    for r in rows:
        assert not (r["side"] == "SELL" and r["htf_trend"] == "up")
        assert not (r["side"] == "BUY" and r["htf_trend"] == "down")
    off = find_stories("EURUSD", h1, "D", {"htf_filter": False})
    assert len(off) >= len(rows)


def ob_start(h, tap_time):
    """Tap time as the origin-bar start value used inside slk.story (same dtype)."""
    st = resample(h, "D")["start"]
    return st.to_numpy()[int((st <= _ts(tap_time)).sum()) - 1]


def test_current_tap_respects_htf_filter():
    from slk.story import _htf_trend, _structure
    h1 = walk(24 * 500, seed=1)
    found = 0
    for end in pd.date_range(h1.index[24 * 300], h1.index[-1], freq="1D")[:60]:
        h = h1[h1.index < end]
        t = current_tap("EURUSD", h, "D")
        if not t:
            continue
        found += 1
        hb = resample(h, "W")
        tr = _htf_trend(hb, _structure(hb, DEFAULT), ob_start(h, t["tap_time"]))
        assert not (t["side"] == "SELL" and tr == "up") and not (t["side"] == "BUY" and tr == "down")
    assert found > 0


def test_timeout_result_uses_last_bar_inside_hold_window():
    h1 = walk()
    cfg = {**DEFAULT, "max_hold": 3}
    ob, cb = resample(h1, "D"), resample(h1, "H4")
    c2o = np.searchsorted(ob["start"].to_numpy(), cb["start"].to_numpy(), side="right") - 1
    checked = 0
    for r in find_stories("EURUSD", h1, "D", cfg):
        if r["outcome"] != "timeout":
            continue
        conf_k = int(np.flatnonzero((cb["end"] == _ts(r["confirm_time"])).to_numpy())[0])
        end_o = min(c2o[conf_k] + cfg["max_hold"], len(ob) - 1)
        last = int(np.flatnonzero(c2o <= end_o)[-1])
        risk = r["stop"] - r["entry_ref"] if r["side"] == "SELL" else r["entry_ref"] - r["stop"]
        move = (r["entry_ref"] - cb["close"].iat[last]) if r["side"] == "SELL" else (cb["close"].iat[last] - r["entry_ref"])
        assert abs(r["result_R"] - round(move / risk, 2)) < 1e-9
        checked += 1
    assert checked > 0


def test_entry_max_trade_bars_is_not_one_bar_too_long():
    h1 = scenario()
    e = find_entries("EURUSD", h1, [story_row(h1)], {**H1ONLY, "max_trade_bars": 1})[0]
    assert e["status"] == "TRIGGERED"
    # one H1 bar of holding = only the fill bar (which can only stop out) -> closed at its close
    assert e["tp1_outcome"] == "timeout" and e["tp1_exit_time"] == e["fill_time"]


def test_hourly_cache_refreshed_when_it_stops_early(tmp_path, monkeypatch):
    now = datetime.utcnow()
    calls = []

    def fake_month(pair, y, m):
        calls.append((y, m))
        return [(datetime(y, m, 1, 1).timestamp(), 1.1, 1.1, 1.1, 1.1)]

    monkeypatch.setattr(data, "CACHE", str(tmp_path))
    monkeypatch.setattr(data, "_month", fake_month)
    stale = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]},
                         index=pd.DatetimeIndex([pd.Timestamp(now.year, 1, 1, tz="UTC")]))
    stale.index.name = "t"
    stale.to_csv(tmp_path / "EURUSD_H1.csv.gz", compression="gzip")
    if now - timedelta(days=7) > datetime(now.year, 1, 1):
        data.hourly("EURUSD", now.year, now.year)
        assert calls  # stale cache for the running year -> downloaded again
    calls.clear()
    full = pd.DataFrame({"open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0], "close": [1.0, 1.0]},
                        index=pd.DatetimeIndex([pd.Timestamp(2019, 1, 1, tz="UTC"), pd.Timestamp(2020, 12, 31, tz="UTC")]))
    full.index.name = "t"
    full.to_csv(tmp_path / "EURUSD_H1.csv.gz", compression="gzip")
    assert len(data.hourly("EURUSD", 2019, 2020)) == 2 and not calls  # complete cache is reused


def _stmts(path):
    text = re.sub(r"--[^\n]*", "", path.read_text())
    return [re.sub(r"\s+", " ", s).strip() for s in text.split(";") if s.strip()]


def test_webapp_fallback_schema_matches_db_schema():
    assert _stmts(ROOT / "webapp" / "schema.sql") == _stmts(ROOT / "db" / "schema.sql")


def test_backtest_workflow_inputs_not_in_scripts_and_failures_not_hidden():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "backtest.yml").read_text())
    steps = wf["jobs"]["backtest"]["steps"]
    for s in steps:
        assert "inputs." not in s.get("run", "")
    for name in ("Backtest", "Entry backtest"):
        run = next(s for s in steps if s.get("name") == name)["run"]
        assert "exit $rc" in run
