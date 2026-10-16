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
    assert "Continuation break: H4 close below the next V-shape" in m and "➤ NEW 0.92903" in m
