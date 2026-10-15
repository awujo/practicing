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


def _t(x):
    if x is None or x == "":
        return None
    if isinstance(x, datetime):
        return x.replace(tzinfo=None)
    return datetime.fromisoformat(str(x).replace("T", " ")[:19])


def standing(rows, story):
    """{'story', 'side' ('BUY'/'SELL'/None), 'since' (confirm time of the first story of this run), 'stories' (how
    many same-side stories in a row), 'last' (row holding the bias, or the one that ended it), 'state'}.
    state: 'story active' | 'target reached, bias continues' | 'no outcome yet, bias continues' |
    'invalidated' | 'ended by flip' | 'none' (never confirmed)."""
    conf = sorted((r for r in rows if r.get("story") == story and _t(r.get("confirm_time")) is not None
                   and r.get("status") in KEEPS + ENDS), key=lambda r: _t(r["confirm_time"]))
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


def all_standing(rows, stories=("M", "W", "D")):
    return [standing(rows, s) for s in stories]


def note(event, row, before, after):
    """One alert line about the standing bias for a story event, or None.
    before/after = standing() of this pair and story TF before / after this run's writes."""
    w = WORD.get(after.get("side")) if after else None
    if event == "CONFIRMED":
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
