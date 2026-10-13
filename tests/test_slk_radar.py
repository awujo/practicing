"""Features adopted from the SLK Radar comparison (knowledge-base/study/compare_slk_radar.md, "Worth adopting" 1-6):
Next Day Rule, clearer alerts + display_tz, early breakout alert, retrace warning, level "formed" date, /terms, entry
alignment (owner: entry_alignment d_h4 / w_d_h4 / off) and the backtest variants. Hand-built candles (winter dates:
17:00 New York = 22:00 UTC) and the synthetic walk; no network."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from slk import backtest, live, settings as SET, story as S
from slk.entry import ALIGN_TFS, _Pair, find_entries
from slk.terms import TERMS, is_terms
from test_bias_rules import OFF, ctx, day, h1_from_h4, h4_closes
from test_engine import walk

NEXT = [1.000, 1.004, 1.007, 1.003, 1.000, 0.999]      # tap day closes above B 0.997: breakout the next day
SAME = [1.000, 1.004, 1.007, 1.000, 0.996, 0.995]      # H4 closes below B inside the tap day, D closes below B
RETRACE = [1.000, 1.004, 1.007, 0.996, 0.998, 0.995]  # same-day break, next H4 closes back above B, D below B


def days(tap_closes, after=(0.998, 0.996, 0.995, 0.994, 0.995, 0.994)):
    """D sell levels A 1.010 / bear OC 1.000 (as test_bias_rules.flip_days), tapped on day 5 (Mon 2023-01-09,
    wick 1.012 on its 3rd H4); H4 point B = 0.997; day 6 (Tue) breaks lower."""
    h4 = day(0.990, 0.9955, 0.9895, 0.995) + day(0.995, 1.0005, 0.9945, 1.000) + day(1.000, 1.0105, 0.9995, 1.010)
    h4 += day(1.010, 1.0102, 0.9995, 1.000)
    h4 += h4_closes(1.000, [0.999, 0.997, 0.995, 0.996, 0.998, 0.997])
    h4 += h4_closes(0.997, tap_closes, {2: 1.012})
    h4 += h4_closes(tap_closes[-1], list(after))
    for _ in range(4):
        h4 += day(after[-1], after[-1] + 0.0005, 0.9895, 0.990)
    return h4


def started(closes, **cfg):
    X = ctx(days(closes), **cfg)
    X.target = lambda *a, **k: 0.980  # no opposite level in this short history: a fixed target
    lv = [l for l in X.levels if l.kind == "A" and np.isclose(l.price, 1.010)][0]
    assert lv.events[0][:2] == (5, "tap")
    return X.start(lv, 5, "standard", "down")


# ------------------------------------------------------------------ 1. Next Day Rule
def test_next_day_rule_flag_and_require():
    """story-line-pt3@1358-1401 / qns-pt2@1946-1962: the H4 breakout should come after the D rejection candle closed."""
    r = started(NEXT)
    assert r["next_day"] is True and r["breakout_time"] == "2023-01-10 02:00" and r["retrace"] is False
    assert started(NEXT, next_day_rule="require")["breakout_time"] == r["breakout_time"]
    s = started(SAME)
    assert s["next_day"] is False and s["breakout_time"] == "2023-01-09 14:00"     # inside the tap day
    assert s["confirm_time"] == "2023-01-09 22:00"                                 # flag: kept, only marked
    assert started(SAME, next_day_rule="require") is None                         # require: rejected
    assert S.DEFAULT["next_day_rule"] == "flag"
    # level "formed" = the D candle at whose close the A-shape existed (bear day 3, opens Wed 22:00 UTC)
    assert r["level_time"] == "2023-01-04 22:00"


@pytest.mark.parametrize("st", ["D", "W", "M"])
def test_next_day_rule_on_walk_all_story_tfs(st):
    """Same rule on M->W, W->D, D->H4: next_day == the breakout candle opens at/after the origin candle's close."""
    h1 = walk(24 * 1500, 3)
    otf = S.STORIES[st][0]
    rows = S.find_stories("EURUSD", h1, st)
    for r in rows:
        if r["rule"].startswith("cadjpy"):
            assert r["next_day"] is None and r["retrace"] is None
            continue
        ob = S.resample(h1, otf)
        i = list(ob["start"].astype(str).str[:16]).index(r["tap_time"])
        tap_end = str(ob["end"].iat[i])[:16]
        assert r["next_day"] == (r["breakout_time"] >= tap_end), r
    req = S.find_stories("EURUSD", h1, st, {"next_day_rule": "require"})
    assert all(r["next_day"] is not False for r in req)
    if st == "D":
        assert any(r["next_day"] is False for r in rows) and len(req) < len(rows)


def test_require_applies_to_current_tap_and_flip():
    """No look-ahead and consistency: under require a same-day breakout is no story, so current_tap does not keep
    reporting it as TAPPED either (it broke out); flips use the same break search."""
    h1 = h1_from_h4(days(SAME))
    cut = h1[h1.index < pd.Timestamp("2023-01-10 22:00", tz="UTC")]
    for rule in ("flag", "require"):
        assert S.current_tap("EURUSD", cut, "D", {**OFF, "next_day_rule": rule}) is None
    X = ctx(days(SAME), next_day_rule="require")
    lv = [l for l in X.levels if l.kind == "A" and np.isclose(l.price, 1.010)][0]
    assert X.break_search(lv, 5) is None and ctx(days(SAME)).break_search(lv, 5) is not None


# ------------------------------------------------------------------ 4. retrace warning
def test_retrace_flag_only():
    """qns-pt2@1946-2030: the breakout day "should not trade back into the breakout zone" -> flagged, not cancelled
    (the D close back through B is the cancel rule, same_bar_close)."""
    r = started(RETRACE)
    assert r["retrace"] is True and r["confirm_time"] == "2023-01-09 22:00" and r["kevin_outcome"] != "invalidated"
    assert started(SAME)["retrace"] is False


# ------------------------------------------------------------------ 2/5. alerts
def test_alert_lines_from_engine_story():
    s = {**started(NEXT), "pair": "EURUSD"}
    row = live.to_row(s, "CONFIRMED")
    assert row["next_day"] is True and row["breakout_time"] == datetime(2023, 1, 10, 2)
    m = live.format_alert("CONFIRMED", row)
    assert m.splitlines()[0] == "SELL · EURUSD · D1→H4"
    assert "Rejected at A-shape KL (D1) @ 1.01000 · formed Thu 5 Jan (D1 candle)" in m
    assert "Rejection candle: D1 Mon 9 Jan (open Sun 8 Jan 23:00 WAT, close Mon 9 Jan 23:00 WAT)" in m
    assert "H4 candle open Tue 10 Jan 03:00 WAT, close Tue 10 Jan 07:00 WAT" in m
    assert "✅ Next Day Rule" in m and "Not an entry signal" in m
    t = live.format_alert("CONFIRMED", live.to_row({**started(RETRACE), "pair": "EURUSD"}, "CONFIRMED"), "UTC")
    assert "⚠ same-day breakout" in t and "⚠ Retrace" in t and "Mon 9 Jan 10:00 UTC" in t


def test_retrace_followup_and_row_compare():
    base = {"pair": "EURUSD", "story": "D", "side": "SELL", "status": "CONFIRMED", "level_kind": "A",
            "level": 1.01, "point_b": 0.997, "target": 0.98, "invalidation": 1.01, "tap_time": datetime(2023, 1, 8, 22),
            "confirm_time": datetime(2023, 1, 10, 22), "rule": "standard", "next_day": True, "retrace": False}
    now = datetime(2023, 1, 11)
    assert live._same(base, {**base, "next_day": 1, "retrace": 0})
    w, a = live.reconcile([{**base, "retrace": True}], [{**base, "retrace": 0}], now)
    assert w and [e for e, _ in a] == ["RETRACE"]
    w, a = live.reconcile([{**base, "retrace": True}], [{**base, "retrace": None}], now)  # row stored before the
    assert w and a == []                                                                  # column: no burst of alerts
    # Validation 5: breakout_time is stored too (a cadjpy row has next_day/retrace None, so only this column
    # differs from a row stored before the migration): rewritten once, silently
    cj = {**base, "rule": "cadjpy", "next_day": None, "retrace": None, "breakout_time": datetime(2023, 1, 9, 18)}
    w, a = live.reconcile([cj], [{**cj, "breakout_time": None}], now)
    assert w == [cj] and a == []
    assert live.reconcile([cj], [dict(cj)], now) == ([], [])
    assert live.ALERT_KEY["RETRACE"] == "alert_confirmed"


# ------------------------------------------------------------------ 3. early breakout alert
def test_early_breakout_alert_once_never_confirmed():
    """H4 closed below B on Tue 02:00-06:00 while the Tuesday D candle is still open -> TAPPED row with _early;
    the alert is sent once; after the D close the story is CONFIRMED by the engine as before."""
    h1 = h1_from_h4(days(NEXT))
    cfg = {**S.DEFAULT, **OFF}
    rows = live.pair_state("EURUSD", h1, pd.Timestamp("2023-01-10 06:30", tz="UTC"), ["D"], cfg)
    tap = [r for r in rows if r["status"] == "TAPPED"]
    assert len(tap) == 1 and tap[0]["_early"] == {"time": datetime(2023, 1, 10, 2), "close": 0.996}
    assert not any(r["status"] == "CONFIRMED" for r in rows)
    early = live.pair_state("EURUSD", h1, pd.Timestamp("2023-01-10 05:30", tz="UTC"), ["D"], cfg)
    assert not any(r.get("_early") for r in early)                                  # that H4 not closed yet
    al, sent = live.early_alerts(rows, {}, "2023-01-10 06:30")
    assert [e for e, _ in al] == ["BREAKOUT"] and list(sent) == ["EURUSD|D|2023-01-08 22:00"]
    assert live.early_alerts(rows, sent, "2023-01-10 07:30")[0] == []              # dedupe: once per story
    assert live.early_alerts(rows, {"old": "2022-01-01T00:00:00+00:00"}, "2023-01-10 07:30")[1].keys() == \
        {"EURUSD|D|2023-01-08 22:00"}                                              # old keys pruned
    assert live.early_alerts([{**tap[0], "no_trade": True}], {}, "2023-01-10 07:30")[0] == []
    m = live.format_alert("BREAKOUT", al[0][1])
    assert "H4 breakout — waiting for the daily close" in m and "NOT confirmed" in m and "Not an entry" in m
    after = live.pair_state("EURUSD", h1, pd.Timestamp("2023-01-10 22:30", tz="UTC"), ["D"], cfg)
    # after the D close the tap broke out: no TAPPED row and no early flag any more (a CONFIRMED story comes only
    # from find_stories; here it has no target in this short history, see started())
    assert not [r for r in after if r["tap_time"] == datetime(2023, 1, 8, 22) and r["status"] == "TAPPED"]
    assert not any(r.get("_early") for r in after)


# ------------------------------------------------------------------ settings
def test_new_settings():
    v = SET.load({})
    assert v["next_day_rule"] == "flag" and v["display_tz"] == "Africa/Lagos"
    assert v["early_breakout_alert"] is False and v["entry_alignment"] == "d_h4"
    assert SET.story_cfg(v)["next_day_rule"] == S.DEFAULT["next_day_rule"]
    from slk import entry
    assert SET.entry_cfg(v)["alignment"] == entry.DEFAULT["alignment"] == "d_h4"
    assert SET.clean("next_day_rule", "REQUIRE") == "require" and SET.clean("display_tz", " UTC ") == "UTC"
    for k, bad in (("next_day_rule", "maybe"), ("display_tz", "Mars/Base"), ("display_tz", "../x"),
                   ("entry_alignment", "w")):
        with pytest.raises(ValueError):
            SET.clean(k, bad)
    assert SET.load({"display_tz": "Nowhere/Land"})["display_tz"] == "Africa/Lagos"
    cfg, ecfg, vals = live.build_cfg({"next_day_rule": "require", "entry_alignment": "off"})
    assert cfg["next_day_rule"] == "require" and ecfg["alignment"] == "off"


# ------------------------------------------------------------------ entry alignment
def test_entry_alignment_d_h4_and_w_d_h4():
    """entry-4@1670-1690 ("daily reject daily, 4 hours break ... in line"), entry3@696-818; w_d_h4 adds the weekly."""
    h1 = walk(24 * 1500, 3)
    st = S.find_stories("EURUSD", h1, "D")
    cont = {}
    for mode in ("off", "d_h4", "w_d_h4"):
        rows = find_entries("EURUSD", h1, st, {"alignment": mode, "entry_models": ["continuation"]})
        cont[mode] = [r for r in rows if r.get("model") == "continuation"]
    assert len(cont["off"]) >= len(cont["d_h4"]) >= len(cont["w_d_h4"]) and len(cont["off"]) > len(cont["w_d_h4"])
    px = _Pair("EURUSD", h1, {**__import__("slk.entry", fromlist=["DEFAULT"]).DEFAULT,
                              "story_cfg": S.DEFAULT, "entry_tfs": {}})
    for mode in ("d_h4", "w_d_h4"):
        for r in cont[mode]:
            want = "down" if r["side"] == "SELL" else "up"
            t = np.datetime64(r["created_time"].replace(" ", "T"), "ns")
            assert all(px.last_break(tf, t) == want for tf in ALIGN_TFS[mode]), r
    # last_break = direction of the last structural break closed by t (story._breaks on the close line)
    H4 = px.bars("H4")
    br = S._breaks(S.structural_swings(H4["close"], S.pivots(H4["close"], S.DEFAULT["swing_pivot"])))
    i, up, _ = br[len(br) // 2]
    assert px.last_break("H4", H4["end"][i]) == ("up" if up else "down")
    assert px.last_break("H4", H4["start"][0]) is None
    # QMR entries are not filtered
    q = lambda m: [r for r in find_entries("EURUSD", h1, st, {"alignment": m, "entry_models": ["qmr"]})]  # noqa
    assert q("off") == q("w_d_h4")


def test_entry_alignment_ignores_forming_h4():
    """Validation 5: live h1 ends inside a forming H4 bar (only its first H1 hour closed). A structural break made
    by that unfinished H4 close must not count as 'the last H4 break' (Kevin: wait for the candle to close)."""
    from slk.candles import resample
    from slk.entry import DEFAULT as EDEF
    h1 = walk(24 * 1500, 3)
    H4 = resample(h1, "H4")
    checked = 0
    for n in range(200, 1200):
        cut = h1[h1.index < H4["start"].iloc[n] + pd.Timedelta(hours=1)]  # first hour of H4 bar n only
        c = resample(cut, "H4")["close"].to_numpy()
        br = S._breaks(S.structural_swings(c, S.pivots(c, S.DEFAULT["swing_pivot"])))
        if not br or br[-1][0] != len(c) - 1:
            continue
        px = _Pair("EURUSD", cut, {**EDEF, "story_cfg": S.DEFAULT, "entry_tfs": {}})
        prev = ("up" if br[-2][1] else "down") if len(br) > 1 else None
        assert px.last_break("H4", px.bars("H4")["end"][-1]) == prev, n
        checked += 1
    assert checked >= 3


# ------------------------------------------------------------------ 6. /terms
def test_terms_text():
    assert is_terms("/terms") and is_terms(" /terms@SlkRadarBot x") and is_terms("/TERMS")
    assert not is_terms("/termsx") and not is_terms("terms") and not is_terms(None) and not is_terms("")
    for w in ("External break", "Point B", "A-shape", "V-shape", "open-close", "Next Day Rule", "TAPPED", "CONFIRMED",
              "TARGET_HIT", "INVALIDATED", "ENDED_FLIP", "CANCELLED", "NO_TRADE", "Retrace", "Early breakout"):
        assert w in TERMS, w
    assert len(TERMS) < 4000  # one Telegram message


# ------------------------------------------------------------------ backtest variants
def test_backtest_variants_side_by_side(monkeypatch, tmp_path):
    h1 = walk(24 * 1500, 3)
    monkeypatch.setattr(backtest.store, "hourly", lambda pair, s, e: h1)
    from slk.entry import DEFAULT as EDEF, ENTRY_TFS
    cfg, ecfg = dict(S.DEFAULT), {**EDEF, "entry_tfs": ENTRY_TFS}
    base, vrows = backtest._variant_job(("EURUSD", 2020, 2025, ["D", "W"], cfg, ecfg))
    assert base == backtest.story_rows("EURUSD", h1, ["D", "W"], cfg, log=False)
    vdf = pd.DataFrame(vrows)
    tab = backtest.variants_table(vdf).set_index("variant")
    names = ["next_day_rule=flag", "next_day_rule=require", "cadjpy_exception=on", "cadjpy_exception=off",
             "entry_alignment=d_h4 (TP1)", "entry_alignment=w_d_h4 (TP2)", "entry_alignment=off (TP1)",
             "  flag: next-day breakouts only", "  flag: same-day breakouts only"]
    for n in names:
        assert n in tab.index, n
    assert list(tab.columns) == ["setting", "value", "trades", "win%", "avg_R", "total_R"]
    # numbers = the engine run directly with that setting (tradable stories only)
    for setting, value, ov in (("next_day_rule", "require", {"next_day_rule": "require"}),
                               ("cadjpy_exception", "off", {"cadjpy_exception": False})):
        d = pd.DataFrame(backtest.story_rows("EURUSD", h1, ["D", "W"], {**cfg, **ov}, log=False))
        d = d[~d["no_trade"].fillna(False).astype(bool)]
        row = tab.loc[f"{setting}={value}"]
        assert row["trades"] == len(d) and np.isclose(row["total_R"], round(d["result_R"].sum(), 1))
        assert np.isclose(row["win%"], round((d["outcome"] == "win").mean() * 100, 1))
    flag = tab.loc["next_day_rule=flag"]
    split = tab.loc[["  flag: next-day breakouts only", "  flag: same-day breakouts only",
                     "  flag: no breakout (cadjpy, n/a)"], "trades"].sum()
    assert flag["trades"] == split and tab.loc["next_day_rule=require", "trades"] < flag["trades"]
    assert tab.loc["entry_alignment=off (TP1)", "trades"] >= tab.loc["entry_alignment=w_d_h4 (TP1)", "trades"]
    path = tmp_path / "REPORT.md"
    backtest.report(pd.DataFrame(base), cfg, path, vdf)
    txt = path.read_text()
    assert "## Variants (side by side, to choose defaults)" in txt and "next_day_rule=require" in txt
    assert "entry_alignment=w_d_h4 (TP2)" in txt and "By story and Next Day Rule" in txt
