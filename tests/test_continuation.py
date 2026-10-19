"""Continuation breaks after the external break (owner 2026-10-16, EURCHF 4h chart) + CONFIRMED announced even when
the story ended between two runs + the target lies beyond the wick already traded (target_unswept)."""
from datetime import datetime

import pandas as pd

from slk import live
from slk.story import DEFAULT

# EURCHF H4 closes 9-15 Oct 2026 (IC Markets): Fri 9 Oct 09:00, 13:00, 17:00 UTC, then every 4 h from Sun 11 Oct 21:00
CLOSES = [0.93131, 0.92903, 0.92974, 0.93020, 0.93064, 0.93161, 0.93114, 0.93133, 0.93104, 0.93077, 0.93086, 0.93135,
          0.93133, 0.93230, 0.93234, 0.93275, 0.93232, 0.93326, 0.93223, 0.93256, 0.93128, 0.92999, 0.93082,
          0.93057, 0.92989, 0.92846, 0.92757]


def bars():
    start = pd.DatetimeIndex(["2026-10-09 09:00", "2026-10-09 13:00", "2026-10-09 17:00"], tz="UTC").append(
        pd.date_range("2026-10-11 21:00", periods=len(CLOSES) - 3, freq="4h", tz="UTC"))
    c = pd.Series(CLOSES)
    return pd.DataFrame({"start": start, "open": c.shift(1).fillna(c[0]), "high": c + 0.0005, "low": c - 0.0005,
                         "close": c})


ROW = {"pair": "EURCHF", "story": "D", "side": "SELL", "status": "CONFIRMED", "point_b": 0.93077, "target": 0.92606,
       "breakout_time": datetime(2026, 10, 14, 21), "confirm_time": datetime(2026, 10, 15, 21),
       "tap_time": datetime(2026, 10, 12, 21), "level": 0.93247, "invalidation": 0.93247, "level_kind": "sweep"}


def test_eurchf_yellow_lines():
    br = live.continuation_breaks(ROW, bars(), DEFAULT)
    assert [(b["level"], b["time"]) for b in br][:2] == [(0.92999, datetime(2026, 10, 15, 9)),
                                                         (0.92903, datetime(2026, 10, 15, 13))]
    assert live.unpack_breaks(live.pack_breaks(br))[0] == {"level": 0.92999, "time": "2026-10-15 09:00"}
    # a buy mirrors it; nothing before the breakout
    assert live.continuation_breaks({**ROW, "breakout_time": None}, bars(), DEFAULT) == []


def test_confirmed_is_announced_before_the_outcome():
    old = {**ROW, "status": "TAPPED", "confirm_time": None}
    new = {**ROW, "status": "TARGET_HIT"}
    _, alerts = live.reconcile([new], [old], pd.Timestamp("2026-10-16 06:00", tz="UTC"))
    assert [ev for ev, _ in alerts] == ["CONFIRMED", "TARGET_HIT"] and alerts[0][1]["_late"]
    m = live.format_alert("CONFIRMED", alerts[0][1])
    assert "it already ended before this run" in m


def test_new_continuation_break_alert():
    br = live.pack_breaks(live.continuation_breaks(ROW, bars(), DEFAULT))
    old = {**ROW, "cont_breaks": "0.92999@2026-10-15 09:00"}
    new = {**ROW, "cont_breaks": br, "confirm_time": datetime(2026, 10, 15, 5)}
    _, alerts = live.reconcile([new], [{**old, "confirm_time": datetime(2026, 10, 15, 5)}],
                               pd.Timestamp("2026-10-15 22:00", tz="UTC"))
    ev, r = alerts[0]
    assert ev == "CONTINUATION" and [b["level"] for b in r["_new_breaks"]] == [0.92903, 0.92828][:len(r["_new_breaks"])]
    m = live.format_alert(ev, r)
    assert "CONTINUATION BREAK: the bias continues" in m and "NEW 0.92903" in m


def _h4(closes, t0="2026-10-12 21:00"):
    c = pd.Series(closes, dtype=float)
    return pd.DataFrame({"start": pd.date_range(t0, periods=len(c), freq="4h", tz="UTC"), "open": c.shift(1).fillna(c[0]),
                         "high": c + 0.01, "low": c - 0.01, "close": c})


NZD = {"pair": "NZDJPY", "story": "D", "side": "SELL", "status": "CONFIRMED", "point_b": 88.839, "target": 88.115,
       "breakout_time": datetime(2026, 10, 13, 9), "confirm_time": datetime(2026, 10, 13, 21),
       "tap_time": datetime(2026, 10, 12, 21), "level": 89.090, "invalidation": 89.090, "level_kind": "flip"}


def test_one_candle_through_several_vs_is_one_break():
    # owner 2026-10-16 NZDJPY: four V's (88.501, 88.487, 88.462, 88.428) cleared by one H4 close read as a repeat
    # after the break price retraced with higher lows (V's 88.428, 88.462, 88.487, 88.501), then one H4 closed below all
    cl = [88.90, 88.80, 88.428, 88.50, 88.462, 88.52, 88.487, 88.55, 88.501, 88.60, 88.30, 88.35]
    br = live.continuation_breaks(NZD, _h4(cl), {**DEFAULT, "b_pivot": 1})
    assert len(br) == 1 and br[0]["n"] == 4 and (br[0]["first"], br[0]["level"]) == (88.501, 88.428)
    txt = live.pack_breaks(br)
    assert live.unpack_breaks(txt) == [{"level": 88.428, "time": br[0]["time"].strftime("%Y-%m-%d %H:%M"), "n": 4,
                                        "first": 88.501}]
    m = live.format_alert("CONFIRMED", {**NZD, "cont_breaks": txt})
    assert sum("88.428" in x for x in m.splitlines()) == 1 and "88.428 (cleared 4 V's from 88.501)" in m


def test_after_target_breaks_go_on_and_the_line_can_end():
    cl = [88.90, 88.80, 88.70, 88.60, 88.30, 88.10, 88.05, 88.20, 88.00, 88.10, 87.90, 88.00]  # V 88.00 below T broken
    r = {**NZD, "status": "TARGET_HIT", "_end_time": datetime(2026, 10, 13, 17)}
    br = live.continuation_breaks(r, _h4(cl), {**DEFAULT, "b_pivot": 1})
    assert any(b["level"] < NZD["target"] for b in br)  # beyond the target: next liquidity
    m = live.format_alert("CONTINUATION", {**r, "cont_breaks": live.pack_breaks(br),
                                           "_new_breaks": live.unpack_breaks(live.pack_breaks(br))[-1:]})
    assert "continues after the target" in m and "(next liquidity)" in m and "After the target: " in m
    # the line ends at the first origin (D) close back above the level after the confirmation
    d = pd.DataFrame({"start": pd.to_datetime(["2026-10-13 21:00", "2026-10-14 21:00", "2026-10-15 21:00"], utc=True),
                      "close": [88.5, 89.2, 89.3]})
    assert live.line_end(r, d) == datetime(2026, 10, 14, 21)
    now = pd.Timestamp("2026-10-16 06:00", tz="UTC")
    _, alerts = live.reconcile([{**r, "line_end": datetime(2026, 10, 14, 21)}], [dict(r)], now)
    assert [ev for ev, _ in alerts] == ["LINE_END"]
    m = live.format_alert("LINE_END", alerts[0][1])
    assert "STORY LINE ENDED after the target" in m and "closed above 89.090" in m
    from slk import standing
    assert standing.standing([{**r, "line_end": datetime(2026, 10, 14, 21)}], "D")["side"] is None
    assert standing.standing([r], "D")["side"] == "SELL"
    assert "Next: an H4 close below the next V-shape continues" in live.format_alert("TARGET_HIT", r)


def test_same_break_on_two_stories_is_sent_once():
    br = "0.92903@2026-10-15 13:00"
    old = [{**ROW, "cont_breaks": None, "confirm_time": datetime(2026, 10, 15, 5)},
           {**ROW, "status": "TARGET_HIT", "tap_time": datetime(2026, 10, 5, 21),
                                          "confirm_time": datetime(2026, 10, 6, 21), "cont_breaks": None}]
    new = [{**o, "cont_breaks": br} for o in old]
    _, alerts = live.reconcile(new, old, pd.Timestamp("2026-10-15 22:00", tz="UTC"))
    assert [(ev, r["tap_time"]) for ev, r in alerts] == [("CONTINUATION", ROW["tap_time"])]


def test_erl_taken_is_bias_but_no_trade():
    r = {**ROW, "no_trade": True, "no_trade_reason": live.ERL_TAKEN}
    assert live.filter_alerts([("CONFIRMED", r)]) == [("CONFIRMED", r)]  # still announced as bias
    assert "selling now is late" in live.format_alert("CONFIRMED", r)
    assert live.entry_rows("EURCHF", None, [{**r, "_story": {}}], {}, finder=lambda *a, **k: 1 / 0) == []


def test_pair_state_excludes_unclosed_continuation_candle(monkeypatch):
    now = pd.Timestamp("2026-10-19 08:00", tz="UTC")  # 09 WAT, before the 10 WAT H4 close
    idx = pd.date_range(pd.Timestamp("2026-09-01", tz="UTC"), now - pd.Timedelta(hours=1), freq="h")
    h1 = pd.DataFrame({k: 0.93 for k in ["open", "high", "low", "close"]}, index=idx)
    story = {"pair": "EURCHF", "story": "D", "side": "SELL", "kevin_outcome": "target",
             "level": 0.94, "B": 0.935, "target": 0.925, "tap_time": ROW["tap_time"],
             "confirm_time": ROW["confirm_time"], "breakout_time": ROW["breakout_time"]}
    monkeypatch.setattr(live, "engine_rows", lambda *a: ([story], None))
    seen = []
    def capture(r, cb, cfg, until):
        seen.extend(cb["start"])
        return []
    monkeypatch.setattr(live, "continuation_breaks", capture)
    live.pair_state("EURCHF", h1, now, ["D"], DEFAULT)
    assert seen
    assert max(seen) == pd.Timestamp("2026-10-19 01:00", tz="UTC")
    assert all(live.candle_end(t, "H4") <= now for t in seen)
