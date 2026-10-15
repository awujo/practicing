"""Standing bias (slk/standing.py): a bias outlives its story's target and ends only when proven otherwise."""
from datetime import datetime

from slk import live, standing as S


def r(day, side="BUY", status="CONFIRMED", story="D"):
    return {"pair": "EURCAD", "story": story, "side": side, "status": status,
            "tap_time": datetime(2026, 10, day, 21), "confirm_time": datetime(2026, 10, day + 1, 21)}


def test_target_hit_keeps_the_bias():
    b = S.standing([r(1, status="TARGET_HIT")], "D")
    assert b["side"] == "BUY" and b["state"] == "target reached, bias continues"


def test_continuation_counts_and_keeps_since():
    b = S.standing([r(1, status="TARGET_HIT"), r(5, status="CANCELLED"), r(9)], "D")
    assert b["side"] == "BUY" and b["stories"] == 3 and b["since"] == datetime(2026, 10, 2, 21)
    assert b["state"] == "story active"


def test_opposite_story_changes_it():
    b = S.standing([r(1, status="TARGET_HIT"), r(5, side="SELL")], "D")
    assert b["side"] == "SELL" and b["stories"] == 1


def test_invalidation_or_flip_ends_it():
    assert S.standing([r(1, status="TARGET_HIT"), r(5, status="INVALIDATED")], "D")["side"] is None
    assert S.standing([r(1, status="ENDED_FLIP")], "D")["state"] == "ended by flip"
    # a TAPPED story (not confirmed) changes nothing; other story TFs are separate
    assert S.standing([r(1, status="TARGET_HIT"), {**r(5, side="SELL", status="TAPPED"), "confirm_time": None},
                       r(7, side="SELL", story="W")], "D")["side"] == "BUY"


def test_alert_notes():
    old = [r(1, status="TARGET_HIT")]
    cont = r(9)
    (ev, x), = live.bias_notes([("CONFIRMED", cont)], old, [cont])
    assert x["_bias_note"].startswith("Bias continues BULLISH (story 2 in a row)")
    chg = r(9, side="SELL")
    (_, y), = live.bias_notes([("CONFIRMED", chg)], old, [chg])
    assert y["_bias_note"] == "BIAS CHANGE: BULLISH → BEARISH"
    hit = r(1, status="TARGET_HIT")
    (_, z), = live.bias_notes([("TARGET_HIT", hit)], [r(1)], [hit])
    assert z["_bias_note"].startswith("Bias stays BULLISH")
    inv = r(1, status="INVALIDATED")
    (_, v), = live.bias_notes([("INVALIDATED", inv)], [r(1)], [inv])
    assert v["_bias_note"].startswith("No standing bias now")
    assert "Bias stays BULLISH" in live.format_alert("TARGET_HIT", {**z, "level": 1.5, "point_b": 1.51,
                                                                     "target": 1.53, "invalidation": 1.5})


def test_daily_against_weekly_bias_is_no_trade():
    """Owner 2026-10-15 GBPJPY: W BUY confirmed + D SELL confirmed both shown as tradable; the D sell is against the
    W bias -> NO_TRADE, and its chain is D1->H4 (not W1->D1->H4)."""
    w = r(1, story="W")
    d = {**r(10, side="SELL"), "chain": "W1\u2192D1\u2192H4"}
    out = live.mark_htf_bias([w, d])
    assert d["no_trade"] and d["no_trade_reason"] == "against W bias (BULLISH)" and d["chain"] == "D1\u2192H4"
    up = r(10)
    live.mark_htf_bias([w, up])
    assert not up.get("no_trade") and up["chain"] == "W1\u2192D1\u2192H4"
    early = r(1, side="SELL")  # confirmed before the W story: no W bias then
    live.mark_htf_bias([r(5, story="W"), early])
    assert not early.get("no_trade")
    off = {**r(10, side="SELL")}
    live.mark_htf_bias([w, off], {"htf_bias_filter": False})
    assert not off.get("no_trade") and off["chain"] == "D1\u2192H4"


def test_story_dropped_by_new_rules_is_cancelled_quietly():
    import pandas as pd
    old = {**r(5), "level": 1.5, "point_b": 1.52, "target": 1.6, "invalidation": 1.5, "id": 1}
    idx = pd.date_range("2024-01-01", "2026-10-15", freq="h", tz="UTC")
    h1 = pd.DataFrame({"open": 1.55, "high": 1.56, "low": 1.54, "close": 1.55}, index=idx)
    writes, alerts = live.reconcile([], [old], pd.Timestamp("2026-10-15 12:00", tz="UTC"), h1, {"max_hold": 9999})
    assert writes[0]["status"] == "CANCELLED" and writes[0]["end_reason"] == S.DROPPED and not alerts
    assert S.standing(writes, "D")["side"] is None  # a dropped story holds no bias
