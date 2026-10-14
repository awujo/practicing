"""Entry model tests on hand-built and random-walk prices (no network)."""
import numpy as np
import pandas as pd

from slk.candles import resample
from slk.entry import find_entries, patterns, _arrays
from slk.story import find_stories

from test_engine import walk

P = 0.0001
T0 = pd.Timestamp("2020-01-06 00:00", tz="UTC")  # Monday


def mk(rows):
    """rows of (open, high, low, close) in pips above 1.1000 -> H1 frame."""
    idx = pd.date_range(T0, periods=len(rows), freq="h")
    a = 1.1 + np.array(rows, dtype=float) * P
    return pd.DataFrame(a, index=idx, columns=["open", "high", "low", "close"])


def leg(frm, to, n):
    """n bars moving from frm to to (pips), 1-pip wicks."""
    out, c = [], frm
    for k in range(1, n + 1):
        o, c = c, frm + (to - frm) * k / n
        out.append((o, max(o, c) + 1, min(o, c) - 1, c))
    return out


def pattern_sell(at):
    """c1 bull to `at`, c2 bear, c3 wick 3 pips above the line then closes below, c4 impulsive bear."""
    return [(at - 5, at + 0.5, at - 6, at),            # c1 bull, close = line
            (at, at + 0.5, at - 6, at - 5),            # c2 bear
            (at - 5, at + 3, at - 7, at - 7),          # c3 rejects: high above line, close below
            (at - 7, at - 7, at - 30, at - 29)]        # c4 impulsive close below c1..c3 lows


def story_row(h1, **kw):
    r = {"pair": "EURUSD", "story": "D", "side": "SELL", "level": 1.2, "target": 1.1 - 120 * P,
         "tap_time": str(h1.index[0])[:16], "breakout_time": str(h1.index[2])[:16],
         "confirm_time": str(h1.index[3])[:16]}
    r.update(kw)
    return r


# hand-built patterns test the pattern mechanics; the D/H4 alignment check (entry_alignment) is tested separately
H1ONLY = {"entry_tfs": {"D": ["H1"], "W": ["H1"], "M": ["H1"]}, "alignment": "off"}


def scenario(retest=True, second=False):
    rows = leg(40, 20, 4)                     # 0-3: breakout leg (bar 2 = external break)
    rows += leg(20, 30, 3)                    # 4-6: first retracement up (top at bar 6)
    rows += leg(30, 10, 4)                    # 7-10
    rows += pattern_sell(15)                  # 11-14: pattern, line at +15
    rows += leg(-14, -10, 2)                  # 15-16 small bounce, no retest yet
    if second:
        rows += leg(-10, 0, 2)                # 17-18 up into a second A-shape
        rows += pattern_sell(2)               # 19-22: newer pattern, line at +2
        rows += leg(-27, -20, 2)
    if retest:
        top = 2 if second else 15
        rows += leg(rows[-1][3], top - 1, 3)  # rally that ends 1 pip under the line
        rows.append((top - 1, top + 0.5, top - 2, top - 1))  # touches the line (fill), no stop
    rows += leg(rows[-1][3], -130, 12)        # sell-off to the target
    rows += leg(-130, -130, 30)
    return mk(rows)


def test_h2_bins_on_17ny_grid():
    d = resample(walk(24 * 10), "H2")
    st = pd.to_datetime(d["start"])
    ny = st.dt.tz_convert("America/New_York")
    assert set(ny.dt.hour % 2) == {1}          # 17:00, 19:00, ... New York
    assert (pd.to_datetime(d["end"]) - st).max() == pd.Timedelta(hours=2)


def test_pattern_detection():
    h1 = mk(leg(0, 10, 10) + pattern_sell(15))
    B = _arrays(resample(h1, "H1"))
    cfg = {"tap_tol_pips": 1.0, "impulse_mult": 1.0, "impulse_lookback": 10}
    pats = patterns(B, True, cfg, P)
    assert [p["c1"] for p in pats] == [10]
    assert abs(pats[0]["line"] - (1.1 + 15 * P)) < 1e-9 and abs(pats[0]["c3x"] - (1.1 + 18 * P)) < 1e-9
    # c3 closing above the line is not a rejection
    rows = leg(0, 10, 10) + pattern_sell(15)
    rows[12] = (10, 18, 8, 16)
    assert patterns(_arrays(resample(mk(rows), "H1")), True, cfg, P) == []
    # c4 that does not close beyond c1..c3 lows is not a breakout
    rows = leg(0, 10, 10) + pattern_sell(15)
    rows[13] = (8, 8, 7, 7.5)
    assert patterns(_arrays(resample(mk(rows), "H1")), True, cfg, P) == []
    assert patterns(B, False, cfg, P) == []    # no V-shape buy pattern here


def test_triggered_entry_stop_tp():
    h1 = scenario()
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    assert e["status"] == "TRIGGERED" and e["tf"] == "H1"
    assert abs(e["entry"] - (1.1 + 15 * P)) < 1e-9
    assert abs(e["stop"] - (1.1 + 19 * P)) < 1e-9 and e["stop_pips"] == 4.0
    assert e["tp1"] <= e["entry"] - 1.5 * 4 * P + 1e-9 and e["tp2"] == 1.1 - 120 * P
    assert e["tp1_outcome"] == "win" and e["tp2_outcome"] == "win"
    assert e["tp2_R"] == e["R_tp2"] == round(135 / 4, 2)


def test_skip_first_retracement():
    h1 = scenario()
    # a breakout so late that the pattern sits before the first retracement top -> no setup on H1
    late = story_row(h1, breakout_time=str(h1.index[10])[:16], confirm_time=str(h1.index[11])[:16])
    e = find_entries("EURUSD", h1, [late], H1ONLY)[0]
    assert e["status"] == "NO_SETUP"
    e = find_entries("EURUSD", h1, [late], {**H1ONLY, "skip_first": False})[0]
    assert e["status"] == "TRIGGERED"


def test_missed_when_no_retest():
    h1 = scenario(retest=False)
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    assert e["status"] == "MISSED" and "tp1_R" not in e


def test_newer_level_replaces_older():
    h1 = scenario(second=True)
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    assert e["status"] == "TRIGGERED" and e["candidates"] == 2
    assert abs(e["entry"] - (1.1 + 2 * P)) < 1e-9


def test_filters_wide_stop_and_pairs():
    h1 = scenario()
    e = find_entries("EURUSD", h1, [story_row(h1)], {**H1ONLY, "max_stop_pips": 3})[0]
    assert e["status"] == "NO_SETUP" and "wide_stop 1" in e["note"]
    e = find_entries("AUDNZD", h1, [story_row(h1, pair="AUDNZD")], H1ONLY)[0]
    assert e["status"] == "SKIPPED"


def test_same_bar_stop_and_tp_is_loss():
    rows = scenario().pipe(lambda d: ((d - 1.1) / P).round(6).to_numpy().tolist())
    h1 = scenario()
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    f = list(h1.index.strftime("%Y-%m-%d %H:%M")).index(e["fill_time"])
    rows[f + 1] = [14, 25, -130, -125]        # next bar spikes through the stop and the target
    h1 = mk(rows)
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    assert e["tp1_outcome"] == "loss" and e["tp2_R"] == -1.0


def test_tf_fallback_and_random_walk():
    h1 = walk()
    for st in ("D", "W"):
        stories = find_stories("EURUSD", h1, st)
        rows = find_entries("EURUSD", h1, stories)
        assert len(rows) == len(stories)
        tfs = {"D": {"H4", "H2", "H1"}, "W": {"D", "H4"}}[st]
        for r in rows:
            assert r["status"] in ("TRIGGERED", "MISSED", "PENDING", "NO_SETUP")
            if r["status"] != "NO_SETUP":
                assert r["tf"] in tfs and 0 < r["stop_pips"] <= 20
                assert r["R_tp1"] >= 1.5 - 1e-9 or r["tp1"] == r["tp2"]
            if r["status"] == "TRIGGERED":
                assert r["tp1_R"] >= -1 and r["tp2_R"] >= -1


# ------------------------------------------------------------------ continuation: breakout on candle 4 or later
CFG = {"tap_tol_pips": 1.0, "impulse_mult": 1.0, "impulse_lookback": 10, "breakout_max_bars": 5}


def base_c1_c3(at):
    """c1 bull to the line, c2 bear, c3 wick 3 pips above the line and close below (the rejection)."""
    return pattern_sell(at)[:3]


def test_breakout_on_candle_4():
    pats = patterns(_arrays(resample(mk(leg(0, 10, 10) + pattern_sell(15)), "H1")), True, CFG, P)
    assert [(p["c1"], p["bo"]) for p in pats] == [(10, 13)]   # bo = c1 + 3 = 4th candle


def test_breakout_on_candle_6():
    rows = leg(0, 10, 10) + base_c1_c3(15)
    rows += [(8, 14, 7, 9), (9, 12, 8, 10)]     # c4, c5: stay under the line (c4 wick 14 = another rejection)
    rows += [(10, 10, -20, -19)]                # c6: impulsive bear close below the lows of c1..c5
    B = _arrays(resample(mk(rows), "H1"))
    pats = patterns(B, True, CFG, P)
    assert [(p["c1"], p["bo"]) for p in pats] == [(10, 15)]
    assert abs(pats[0]["c3x"] - (1.1 + 18 * P)) < 1e-9       # stop side = highest wick c3..c5
    assert patterns(B, True, {**CFG, "breakout_max_bars": 2}, P) == []   # c6 is 3 bars after c3
    assert patterns(B, True, {**CFG, "breakout_max_bars": 1}, P) == []   # old rule: 4th candle only


def test_close_back_through_line_before_breakout_is_invalid():
    rows = leg(0, 10, 10) + base_c1_c3(15)
    rows += [(8, 17, 7, 16)]                    # c4 closes back ABOVE the line (16 > 15)
    rows += [(16, 16, -20, -19)]                # c5 impulsive break: too late, level is dead
    assert patterns(_arrays(resample(mk(rows), "H1")), True, CFG, P) == []


def test_candle_6_entry_triggers_with_wider_stop():
    rows = leg(40, 20, 4) + leg(20, 30, 3) + leg(30, 10, 4)      # breakout leg, first retracement, down
    rows += base_c1_c3(15) + [(8, 16, 7, 9), (9, 12, 8, 10), (10, 10, -15, -14)]
    rows += leg(-14, 14, 4) + [(14, 15.5, 13, 14)]               # retest touches the line
    rows += leg(14, -130, 12) + leg(-130, -130, 30)
    h1 = mk(rows)
    e = find_entries("EURUSD", h1, [story_row(h1)], {**H1ONLY, "entry_models": ["continuation"]})[0]
    assert e["status"] == "TRIGGERED" and e["model"] == "continuation" and e["bo_candle"] == 6
    assert abs(e["entry"] - (1.1 + 15 * P)) < 1e-9 and abs(e["stop"] - (1.1 + 19 * P)) < 1e-9


# ------------------------------------------------------------------ QMR (Quasimodo Reversal)
def mirror(rows):
    """Sell scenario -> buy scenario (prices negated, high and low swapped)."""
    return [(-o, -l, -h, -c) for o, h, l, c in rows]


def qmr_rows(extra_continuation=False):
    rows = leg(0, 30, 6)              # 0-5: up to the SHOULDER (close 30, bar 5)
    rows += leg(30, 15, 4)            # 6-9: NECK (close 15, bar 9)
    rows += leg(15, 40, 5)            # 10-14: HEAD (close 40 > shoulder = sweep, bar 14)
    rows += leg(40, 5, 5)             # 15-19: bar 18 closes 12 < neck = neck break
    rows += leg(5, 14, 3)             # 20-22: back up towards the zone
    rows += pattern_sell(20)          # 23-26: H1 level 20 inside the zone, c3 wick 23 rejects, c4 breaks
    if extra_continuation:
        rows += leg(-9, -10, 2) + pattern_sell(-5)    # 27-32: newer continuation level at -5 (QMR still pending)
    else:
        rows += leg(-9, -5, 2)
    rows += leg(rows[-1][3], 19, 3) + [(19, 20.5, 18, 19)]    # retest of the QMR line (fill), stop 24 untouched
    rows += leg(19, -130, 12) + leg(-130, -130, 30)
    return rows


def qmr_story(h1, side="SELL"):
    sgn = 1 if side == "SELL" else -1
    return story_row(h1, side=side, level=1.1 + sgn * 0.01, target=1.1 - sgn * 120 * P,
                     breakout_time=str(h1.index[18])[:16], confirm_time=str(h1.index[19])[:16])


QMR_ONLY = {**H1ONLY, "entry_models": ["qmr"]}


def test_qm_structure_sell():
    from slk.entry import qm_structures
    from slk.structure import pivots
    B = _arrays(resample(mk(qmr_rows()), "H1"))
    qs = qm_structures(B, pivots(B["close"], 2), True, 30)
    q = qs[0]
    assert (q["shoulder_i"], q["neck_i"], q["head_i"], q["brk"]) == (5, 9, 14, 18)
    assert abs(q["shoulder"] - (1.1 + 30 * P)) < 1e-9 and abs(q["neck"] - (1.1 + 15 * P)) < 1e-9
    assert abs(q["head_x"] - (1.1 + 41 * P)) < 1e-9


def test_qmr_sell():
    h1 = mk(qmr_rows())
    e = find_entries("EURUSD", h1, [qmr_story(h1)], QMR_ONLY)[0]
    assert e["status"] == "TRIGGERED" and e["model"] == "qmr" and e["tf"] == "H1" and e["qm_tf"] == "H1"
    assert abs(e["entry"] - (1.1 + 20 * P)) < 1e-9
    # head stop (42) would be 22 pips > max 20 -> the trigger line's own stop: its zone (c1..c3 wicks, top = the
    # c3 rejection wick 23) + 1
    assert e["stop_at"] == "zone" and abs(e["stop"] - (1.1 + 24 * P)) < 1e-9
    assert e["tp2_outcome"] == "win"
    e = find_entries("EURUSD", h1, [qmr_story(h1)], {**QMR_ONLY, "max_stop_pips": 25})[0]
    assert e["stop_at"] == "head" and abs(e["stop"] - (1.1 + 42 * P)) < 1e-9
    # no tap before the neck break -> not this story's QM
    late = {**qmr_story(h1), "tap_time": str(h1.index[19])[:16]}
    assert find_entries("EURUSD", h1, [late], QMR_ONLY)[0]["status"] == "NO_SETUP"


def test_qmr_buy():
    h1 = mk(mirror(qmr_rows()))
    e = find_entries("EURUSD", h1, [qmr_story(h1, "BUY")], QMR_ONLY)[0]
    assert e["status"] == "TRIGGERED" and e["model"] == "qmr" and e["side"] == "BUY"
    assert abs(e["entry"] - (1.1 - 20 * P)) < 1e-9 and abs(e["stop"] - (1.1 - 24 * P)) < 1e-9
    assert e["tp2_outcome"] == "win"


def test_qmr_needs_zone_reaction():
    rows = qmr_rows()
    for k in range(20, 23):                 # retrace stays far below the neck (15): no zone touch
        rows[k] = tuple(x - 8 for x in rows[k])
    rows[23:27] = pattern_sell(8)           # H1 level at 8, rejection wick 11 < neck 15 - tol
    h1 = mk(rows)
    assert find_entries("EURUSD", h1, [qmr_story(h1)], QMR_ONLY)[0]["status"] == "NO_SETUP"


def test_qmr_ranks_above_newer_continuation():
    h1 = mk(qmr_rows(extra_continuation=True))
    st = qmr_story(h1)
    both = find_entries("EURUSD", h1, [st], H1ONLY)[0]
    assert both["candidates"] == 2 and both["status"] == "TRIGGERED" and both["model"] == "qmr"
    assert abs(both["entry"] - (1.1 + 20 * P)) < 1e-9
    cont = find_entries("EURUSD", h1, [st], {**H1ONLY, "entry_models": ["continuation"]})[0]
    assert cont["status"] == "TRIGGERED" and cont["model"] == "continuation"
    assert abs(cont["entry"] - (1.1 - 5 * P)) < 1e-9   # without QMR the newer level is used


# ------------------------------------------------------------------ entry diagnosis 2026-10-14 (REVIEW.md)
def zone_rows():
    """scenario() with c2's wick 8 pips above the line (c3 rejects at +3): the level zone is wider than c3."""
    rows = scenario().pipe(lambda d: ((d - 1.1) / P).round(6).to_numpy().tolist())
    rows[12] = [15, 23, 9, 10]                # c2 bear, wick to +23 (line +15)
    return mk(rows)


def test_stop_covers_level_zone():
    """Kevin's default stop is beyond the whole invalidation zone (c1..breakout-1 wicks), not only c3's wick
    [T e3@247-385, q1@1497-1660]. Before the fix the stop sat at c3 + 1 = +19, inside c2's wick (+23)."""
    h1 = zone_rows()
    B = _arrays(resample(h1, "H1"))
    p = [q for q in patterns(B, True, {**CFG, "breakout_max_bars": 0}, P) if q["c1"] == 11][0]
    assert abs(p["zx"] - (1.1 + 23 * P)) < 1e-9 and abs(p["c3x"] - (1.1 + 18 * P)) < 1e-9
    cont = {**H1ONLY, "entry_models": ["continuation"]}
    e = find_entries("EURUSD", h1, [story_row(h1)], cont)[0]
    assert e["status"] == "TRIGGERED" and e["stop_at"] == "zone"
    assert abs(e["stop"] - (1.1 + 24 * P)) < 1e-9 and e["stop_pips"] == 9.0
    # zone wider than max_stop_pips -> stop on the rejecting candle ("if the zone is too big")
    e = find_entries("EURUSD", h1, [story_row(h1)], {**cont, "max_stop_pips": 6})[0]
    assert e["stop_at"] == "rejection" and abs(e["stop"] - (1.1 + 19 * P)) < 1e-9
    # old rule kept only for the golden test
    e = find_entries("EURUSD", h1, [story_row(h1)], {**cont, "stop_at": "rejection"})[0]
    assert e["stop_at"] == "rejection" and e["stop_pips"] == 4.0


def test_stop_never_inside_the_pattern_random_walk():
    """Every zone stop lies beyond all wicks c1..breakout-1 of its pattern (+ the 1-pip buffer)."""
    h1 = walk()
    n = 0
    for r in find_entries("EURUSD", h1, find_stories("EURUSD", h1, "D"), {"alignment": "off"}):
        if r.get("model") != "continuation" or r.get("stop_at") != "zone":
            continue
        B = resample(h1, r["tf"])
        k = list(pd.to_datetime(B["start"]).dt.strftime("%Y-%m-%d %H:%M")).index(r["c1_time"])
        seg = B.iloc[k:k + r["bo_candle"] - 1]
        if r["side"] == "SELL":
            assert r["stop"] >= seg["high"].max() + P - 1e-9
        else:
            assert r["stop"] <= seg["low"].min() - P + 1e-9
        n += 1
    assert n > 0


def test_no_entry_after_story_end():
    """A story that ended (flip #29 / invalidation / target, slk.story end_time) takes no new entry: before the fix
    14% of the fills on the offline pairs came after a flip had ended the story."""
    h1 = scenario()
    st = story_row(h1)
    assert find_entries("EURUSD", h1, [st], H1ONLY)[0]["status"] == "TRIGGERED"
    ended = {**st, "end_time": str(h1.index[16])[:16], "kevin_outcome": "ended_flip"}   # before the retest (~bar 20)
    e = find_entries("EURUSD", h1, [ended], H1ONLY)[0]
    assert e["status"] in ("MISSED", "NO_SETUP")
    assert find_entries("EURUSD", h1, [ended], {**H1ONLY, "story_end": False})[0]["status"] == "TRIGGERED"


def test_qm_known_waits_for_head_pivot():
    """A neck break on the bar right after the head: the QM exists only once the head pivot is confirmed."""
    from slk.entry import qm_known
    assert qm_known({"brk": 15, "head_i": 14}, 2) == 16
    assert qm_known({"brk": 18, "head_i": 14}, 2) == 18


def test_spread_on_bid_candles():
    """Candles are BID. spread_pips: a SELL stops at ask = bid + spread; a BUY limit fills at ask."""
    h1 = scenario()
    e = find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]
    assert e["status"] == "TRIGGERED" and e["tp1_outcome"] == "win"
    rows = h1.pipe(lambda d: ((d - 1.1) / P).round(6).to_numpy().tolist())
    f = list(h1.index.strftime("%Y-%m-%d %H:%M")).index(e["fill_time"])
    rows[f + 1] = [14, 18.5, 13, 14]          # bid high 18.5: 0.5 pip under the stop (19)
    h1 = mk(rows)
    assert find_entries("EURUSD", h1, [story_row(h1)], H1ONLY)[0]["tp1_outcome"] == "win"
    assert find_entries("EURUSD", h1, [story_row(h1)], {**H1ONLY, "spread_pips": 1.0})[0]["tp1_outcome"] == "loss"
    hb = mk(mirror(scenario().pipe(lambda d: ((d - 1.1) / P).round(6).to_numpy().tolist())))
    sb = story_row(hb, side="BUY", target=1.1 + 120 * P)
    assert find_entries("EURUSD", hb, [sb], H1ONLY)[0]["status"] == "TRIGGERED"
    # the buy retest's bid low goes 0.5 pip through the line: the ask (bid + spread) reaches it only if spread < 0.5
    assert find_entries("EURUSD", hb, [sb], {**H1ONLY, "spread_pips": 0.4})[0]["status"] == "TRIGGERED"
    assert find_entries("EURUSD", hb, [sb], {**H1ONLY, "spread_pips": 1.0})[0]["status"] == "MISSED"
