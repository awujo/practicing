"""Standing bias: the direction a pair is in on one story timeframe, which outlives the story that set it.

Owner 2026-10-15: "a bias remains a bias until proven otherwise ... even when price gets to the target the bias can
keep being correct". Kevin [T story-line-pt4@1925-1967: after the D break "since we are still bearish ... price is
still doing continue ... no buy indication ... price is not ready to buy yet ... if there is going to be a buy
intention, after this weekly [reject] we are going to see daily breakout like this, we now know that price is ready
to buy now"; all-in-1@1249-1290: "we are still bullish on weekly ... because we are not close below this body";
weekly-recap@151: "when the trend is bearish we look for sells"].

So per pair and story TF:
- a CONFIRMED story sets the bias to its side (a new same-side story = continuation, the bias carries on);
- target reached / no outcome in time (TARGET_HIT, CANCELLED) do NOT end it;
- it ends only when proven otherwise: a confirmed story the other way (bias change), or the story that holds it is
  INVALIDATED (origin close back through its level) or ENDED_FLIP (opposite level rejected + broken) -> no bias until
  the next confirmed story.
Stdlib only (the Mini App imports it). Rows = table `bias` rows (dicts) of one pair, any status.
"""
from datetime import datetime

KEEPS = ("CONFIRMED", "TARGET_HIT", "CANCELLED")   # the bias stands after these
ENDS = ("INVALIDATED", "ENDED_FLIP")                # proven otherwise
WORD = {"BUY": "BULLISH", "SELL": "BEARISH"}
DROPPED = "no longer a story under the current rules/settings"  # end_reason of a story the engine stopped reporting


def _t(x):
    if x is None or x == "":
        return None
    if isinstance(x, datetime):
        return x.replace(tzinfo=None)
    return datetime.fromisoformat(str(x).replace("T", " ")[:19])


def pullback(r):
    """A story against its own TF's structure trend at the tap (pullback_levels: the TF retracing toward the higher
    TF's levels) = a retracement inside the bias, not a new bias (owner 2026-10-15, GBPJPY W BUY in a bearish W)."""
    t = r.get("trend")
    return t in ("up", "down") and (r.get("side") == "BUY") != (t == "up")


def _from_stories(conf, story):
    if not conf:
        return {"story": story, "side": None, "since": None, "stories": 0, "last": None, "state": "none"}
    last = conf[-1]
    if last["status"] in ENDS:
        return {"story": story, "side": None, "since": None, "stories": 0, "last": last,
                "state": "invalidated" if last["status"] == "INVALIDATED" else "ended by flip"}
    run = [last]
    for r in reversed(conf[:-1]):
        if r["side"] != last["side"] or r["status"] in ENDS:
            break
        run.append(r)
    state = {"CONFIRMED": "story active", "TARGET_HIT": "target reached, bias continues",
             "CANCELLED": "no outcome yet, bias continues"}[last["status"]]
    return {"story": story, "side": last["side"], "since": _t(run[-1]["confirm_time"]), "stories": len(run),
            "last": last, "state": state}


def standing(rows, story, trend=None):
    """{'story', 'side' ('BUY'/'SELL'/None), 'since' (confirm time of the first story of this run), 'stories' (how
    many same-side stories in a row), 'last' (row holding the bias, or the one that ended it), 'state',
    'pullback' (an active counter-trend story, or None)}.
    Stories set the bias (pullback stories do not: they are retracements inside it). `trend` = the TF's structure
    trend now (slk.story.tf_trend): when it points the other way, the structure has broken (BOS) and the bias is the
    structure's side until a story confirms ("will it become bearish on weekly if we close below that body?
    Exactly" [T all-in-1@1257-1267])."""
    conf = sorted((r for r in rows if r.get("story") == story and _t(r.get("confirm_time")) is not None
                   and r.get("status") in KEEPS + ENDS and r.get("end_reason") != DROPPED),
                  key=lambda r: _t(r["confirm_time"]))
    b = _from_stories([r for r in conf if not pullback(r)], story)
    pb = [r for r in conf if pullback(r) and r["status"] == "CONFIRMED"]
    b["pullback"] = pb[-1] if pb else None
    if trend in ("up", "down"):
        side = "BUY" if trend == "up" else "SELL"
        if b["side"] != side:
            b.update(side=side, since=None, stories=0,
                     state=f"{'bullish' if side == 'BUY' else 'bearish'} structure (break of structure), no story yet")
    if b["pullback"] is not None and b["side"] and b["pullback"]["side"] != b["side"]:
        b["state"] += f" \u00b7 pullback {b['pullback']['side']} story active (retracement)"
    return b


def all_standing(rows, stories=("M", "W", "D")):
    return [standing(rows, s) for s in stories]


def note(event, row, before, after):
    """One alert line about the standing bias for a story event, or None.
    before/after = standing() of this pair and story TF before / after this run's writes."""
    w = WORD.get(after.get("side")) if after else None
    if event == "CONFIRMED":
        if after and after.get("side") and after["side"] != row["side"]:
            return f"Pullback {row['side']} inside a {WORD[after['side']]} bias (retracement, not a bias change)"
        if before and before.get("side") == row["side"]:
            return f"Bias continues {WORD[row['side']]} (story {after.get('stories', 1)} in a row) · continuation"
        if before and before.get("side"):
            return f"BIAS CHANGE: {WORD[before['side']]} → {WORD[row['side']]}"
        return f"New bias: {WORD[row['side']]}"
    if event == "TARGET_HIT" and w:
        return (f"Bias stays {w}: a target is not the end of the bias. It ends only on a confirmed opposite story "
                f"or a close back through the level")
    if event in ENDS and not w:
        return "No standing bias now: wait for the next confirmed story"
    return None
