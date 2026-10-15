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
