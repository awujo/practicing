"""REVIEW #26, #29, #30, #31 (STRATEGY v0.6): most recent level, story ends early by a flip, targets on the same or a
higher TF, overlap / alignment / CADJPY exceptions. Hand-built candles (H4 -> H1, winter dates so the 17:00 New York
close is 22:00 UTC) plus properties on the synthetic walk."""
import json

import numpy as np
import pandas as pd

import engine_golden as G
from slk import story as S
from slk.levels import Level
from slk.structure import pivots, structural_swings
from test_engine import walk


# ------------------------------------------------------------------ hand-built candles
def h1_from_h4(h4, start="2023-01-02"):
    """H1 candles whose H4 bars are exactly `h4` [(o, h, l, c)], 6 per trading day (Mon-Fri)."""
    days = pd.bdate_range(start, periods=(len(h4) + 5) // 6)
    idx, rows = [], []
    for n, (o, h, l, c) in enumerate(h4):
        t0 = pd.Timestamp(days[n // 6], tz="UTC") - pd.Timedelta(hours=2) + pd.Timedelta(hours=4 * (n % 6))
        for i, r in enumerate([(o, h, l, o), (o, o, o, o), (o, o, o, o), (o, max(o, c), min(o, c), c)]):
            idx.append(t0 + pd.Timedelta(hours=i))
            rows.append(r)
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=pd.DatetimeIndex(idx))


def day(o, h, l, c):
    """One D candle as 6 H4 candles: a straight walk o -> c, the low wick on the 3rd and the high wick on the 4th."""
    pts = [o + (c - o) * (i + 1) / 6 for i in range(6)]
    out, prev = [], o
    for i, x in enumerate(pts):
        hi, lo = max(prev, x), min(prev, x)
        out.append((prev, h if i == 3 else hi, l if i == 2 else lo, x))
        prev = x
    return out


def h4_closes(o, closes, hi=None):
    """H4 candles from a close path; `hi` = {position: high wick} (no other wicks)."""
    out, prev = [], o
    for i, x in enumerate(closes):
        h = (hi or {}).get(i, max(prev, x))
        out.append((prev, h, min(prev, x), x))
        prev = x
    return out


OFF = {"trend_filter": False, "htf_filter": False}


def ctx(h4, **cfg):
    return S._Ctx("EURUSD", h1_from_h4(h4), "D", {**S.DEFAULT, **OFF, **cfg})


# ------------------------------------------------------------------ #29 flip
def flip_days(break_down=True):
    """D: A-shape sell level at 1.0100 (bull day 2 closes the peak, bear day 3), tapped on day 5 (wick 1.0120,
    close 0.999); H4 point B = 0.997 (last H4 close valley before the touching H4 bar); day 6 closes H4 0.996 below B
    and the day closes 0.994 (or stays above B when break_down=False)."""
    h4 = day(0.990, 0.9955, 0.9895, 0.995) + day(0.995, 1.0005, 0.9945, 1.000) + day(1.000, 1.0105, 0.9995, 1.010)
    h4 += day(1.010, 1.0102, 0.9995, 1.000)
    h4 += h4_closes(1.000, [0.999, 0.997, 0.995, 0.996, 0.998, 0.997])
    h4 += h4_closes(0.997, [1.000, 1.004, 1.007, 1.003, 1.000, 0.999], {2: 1.012})
    h4 += h4_closes(0.999, [0.998, 0.996, 0.995, 0.994, 0.995, 0.994] if break_down else
                    [0.999, 0.998, 0.9985, 0.999, 0.9975, 0.998])
    for _ in range(4):
        h4 += day(0.994, 0.9945, 0.9895, 0.990) if break_down else day(0.998, 0.9985, 0.9978, 0.998)
    return h4


def test_flip_ends_a_buy_story_at_a_d_sell_level_on_the_way():
    """story-line-pt2@1779-1832: D KL on the way, rejected the other way + H4 break the other way = story over."""
    X = ctx(flip_days())
    lv = [l for l in X.levels if l.kind == "A" and np.isclose(l.price, 1.010)]
    assert lv and lv[0].events[0][:2] == (5, "tap")            # tap-reject-close on day 5
    buy = Level(0.9000, "buy", "V", 0)                          # a running BUY story: origin 0.90, target 1.10
    got = X.flip_scan(buy, 1.1000, 4, 10)
    assert got is not None
    ck, fo, f, fB = got
    # the sell levels tapped on day 5: A 1.010 and the bear open-close 1.000 (most recent wins, as for a start)
    assert fo == 5 and f is X.choose(5, "down") and np.isclose(f.price, 1.000) and np.isclose(fB, 0.997)
    assert X.c2o[ck] == 6 and ck == X.first_k[7] - 1           # known at the close of day 6 (same-day D close)
    assert X.flip_scan(buy, 0.9990, 4, 10) is None             # levels beyond the target: not "on the way"
    assert X.flip_scan(Level(0.9, "sell", "A", 0), 0.8, 4, 10) is None  # same side as the story: no flip
    assert ctx(flip_days(break_down=False)).flip_scan(buy, 1.1000, 4, 10) is None  # no H4 break: still bullish


def test_flip_stories_on_walk():
    for seed in (1, 3, 5):
        h1 = walk(24 * 900, seed)
        rows = S.find_stories("EURUSD", h1, "D")
        ended = [i for i, r in enumerate(rows) if r["kevin_outcome"] == "ended_flip"]
        assert ended, seed
        for i in ended:
            r = rows[i]
            assert r["end_reason"].startswith("flip: D") and r["end_time"] >= r["confirm_time"]
            assert r["outcome"] in ("win", "loss", "flip")
            nxt = [x for x in rows[i + 1:] if x["rule"] == "flip"][:1]
            for x in nxt:  # the opposite story that started at the flip level
                if x["tap_time"] <= r["end_time"]:
                    assert x["side"] != r["side"]
        off = S.find_stories("EURUSD", h1, "D", {"flip_end": False})
        assert all(r["kevin_outcome"] != "ended_flip" and r["rule"] != "flip" for r in off)


# ------------------------------------------------------------------ #26 most recent level
def test_most_recent_fresh_level_formed_before_the_tap():
    """story-line-pt2@897-1000: mark the most recent fresh level, ignore older ones; levels formed after the tap do
    not count."""
    X = ctx(flip_days())
    older = Level(1.0300, "sell", "A", 2, [(8, "tap", True)])
    newer = Level(1.0400, "sell", "OC", 5, [(9, "tap", True)])
    later = Level(1.0500, "sell", "A", 10, [(12, "tap", True)])  # formed after the taps of bars 8 and 9
    X.levels = [older, newer, later]
    X.lv = S._LevelSet(pd.DataFrame({"start": X.o_start, "end": X.o_end}), X.levels)
    X.taps = {8: [older], 9: [newer], 12: [later]}
    assert X.choose(8, "down") is None                        # older level tapped while a newer fresh one exists
    assert X.choose(9, "down") is newer
    X.cfg = {**X.cfg, "most_recent_level": False}
    assert X.choose(8, "down") is older
    X.cfg = {**X.cfg, "most_recent_level": True}
    X.levels.remove(newer)
    X.lv = S._LevelSet(pd.DataFrame({"start": X.o_start, "end": X.o_end}), X.levels)
    assert X.choose(8, "down") is older                       # `later` (born 10) did not exist at the tap


def test_newer_level_closed_through_on_the_tap_bar_does_not_block():
    """Validation 4 (story-line-pt2@940-990: "this one already abused ... not fresh. The nearest fresh key level is
    this one"): price runs through a newer level, closes beyond it and rejects at the older one on the same bar ->
    the older level is the nearest FRESH one. A newer level only TAPPED on that bar still wins (_pick)."""
    X = ctx(flip_days())
    older = Level(1.0300, "sell", "A", 2, [(8, "tap", True)])
    newer = Level(1.0250, "sell", "OC", 5, [(8, "break", False)])  # closed through on the tap bar
    X.levels = [older, newer]
    X.lv = S._LevelSet(pd.DataFrame({"start": X.o_start, "end": X.o_end}), X.levels)
    X.taps = {8: [older]}
    assert X.choose(8, "down") is older
    newer.events[0] = (8, "tap", True)                               # only tapped: it is the most recent fresh one
    X.lv = S._LevelSet(pd.DataFrame({"start": X.o_start, "end": X.o_end}), X.levels)
    assert X.choose(8, "down") is None


def test_forming_weekly_bar_is_not_closed():
    """Validation 4 (no look-ahead, live = backtest): live data stop at the last closed D bar, so mid-week the last
    W bar's 'end' is only the last hour seen. It must not count as a closed weekly candle (overlap: "weekly judged
    after its close"; higher-TF targets: levels as of the last CLOSED bar)."""
    from slk.candles import nominal_end
    h1 = h1_from_h4(cad_days())                     # Mon 2023-01-02 .. ; cut after Wednesday's D close
    cut = h1[h1.index < pd.Timestamp("2023-01-04 22:00", tz="UTC")]
    X = S._Ctx("EURUSD", cut, "D", {**S.DEFAULT, **OFF})
    tf, H = X.higher[0]
    assert tf == "W" and H.end[-1] == nominal_end(H.start[-1], "W") == pd.Timestamp("2023-01-06 22:00", tz="UTC")
    assert H.closed_upto(X.o_end[-1]) == len(H.start) - 2
    assert nominal_end(pd.Timestamp("2023-01-03 22:00", tz="UTC"), "D") == pd.Timestamp("2023-01-04 22:00", tz="UTC")
    assert nominal_end(pd.Timestamp("2023-01-01 22:00", tz="UTC"), "M") == pd.Timestamp("2023-01-31 22:00", tz="UTC")
    full = S._Ctx("EURUSD", h1, "D", {**S.DEFAULT, **OFF}).higher[0][1]
    assert full.end[0] == pd.Timestamp("2023-01-06 22:00", tz="UTC")  # a finished week keeps its real close


# ------------------------------------------------------------------ #31c CADJPY
def cad_days(sweep=True):
    """OC buy level at 1.0040 (bear days 0-1 to the close valley 1.000, bull days 2-3: line at the close of day 2),
    day 4 bear low 1.0055; day 5 wicks to 1.0030 (below the previous low and into the level) and closes 1.0070."""
    h4 = day(1.010, 1.0105, 1.0045, 1.005) + day(1.005, 1.0052, 0.9995, 1.000) + day(1.000, 1.0042, 0.9998, 1.004)
    h4 += day(1.004, 1.0083, 1.0038, 1.008) + day(1.008, 1.0082, 1.0055 if sweep else 1.0025, 1.006)
    h4 += day(1.006, 1.0075, 1.0030, 1.007) + day(1.007, 1.0090, 1.0065, 1.0085)
    for _ in range(4):
        h4 += day(1.0085, 1.0095, 1.0080, 1.009)
    return h4


def test_cadjpy_exception_conditions():
    """cadjpy-bd@400-995: W bullish + D sweeps the previous day low into a D open-close level, closes back above."""
    X = ctx(cad_days())
    oc = [l for l in X.levels if l.kind == "OC" and l.side == "buy" and np.isclose(l.price, 1.004)]
    assert oc and np.isclose(oc[0].price, 1.004) and oc[0].events[0][:2] == (5, "tap")
    # Validation 4: the daily must already have flipped bullish ("after the bullish close above this guy, price
    # did a sweep of previous day low", cadjpy-bd@440-560): a D body close above a sell level shortly before
    assert not X.cadjpy(oc[0], 5, "up")                                       # no D flip yet: H4 breakout needed
    X.levels.append(Level(1.0075, "sell", "A", 1, [(3, "break", False)]))     # day 3 closes above a D sell level
    X._flips = None
    assert X.cadjpy(oc[0], 5, "up")
    X.cfg = {**X.cfg, "max_wait": 1}
    assert not X.cadjpy(oc[0], 5, "up")                                       # that flip is too old
    X.cfg = {**X.cfg, "max_wait": S.DEFAULT["max_wait"]}
    assert not X.cadjpy(oc[0], 5, "down") and not X.cadjpy(oc[0], 5, "range")  # needs the weekly trend
    v = Level(oc[0].price, "buy", "V", oc[0].born)
    assert not X.cadjpy(v, 5, "up")                                            # open-close / flipped zone only
    Z = ctx(cad_days(), cadjpy_exception=False)
    Z.levels.append(Level(1.0075, "sell", "A", 1, [(3, "break", False)]))
    assert not Z.cadjpy(oc[0], 5, "up")
    Y = ctx(cad_days(sweep=False))                                             # previous low already lower: no sweep
    Y.levels.append(Level(1.0075, "sell", "A", 1, [(3, "break", False)]))
    assert not Y.cadjpy(Level(1.004, "buy", "OC", 4), 5, "up")


def test_cadjpy_stories_on_walk():
    n = 0
    for seed in (1, 3):
        h1 = walk(24 * 900, seed)
        ob = S.resample(h1, "D")
        st = pd.to_datetime(ob["start"]).dt.strftime("%Y-%m-%d %H:%M").tolist()
        for r in S.find_stories("EURUSD", h1, "D"):
            if not r["rule"].startswith("cadjpy"):
                continue
            n += 1
            j = st.index(r["tap_time"])
            assert r["level_kind"] in ("OC", "flip") and r["break_kind"] == "none"
            assert r["htf_trend"] == ("up" if r["side"] == "BUY" else "down")
            if r["side"] == "BUY":  # swept the previous day's low, closed back above it and the level
                assert ob["low"].iat[j] < ob["low"].iat[j - 1] < ob["close"].iat[j] and ob["close"].iat[j] > r["level"]
            else:
                assert ob["high"].iat[j] > ob["high"].iat[j - 1] > ob["close"].iat[j] and ob["close"].iat[j] < r["level"]
            # confirmed at the close of the tap day: no H4 breakout waited for
            assert pd.Timestamp(r["confirm_time"]) == pd.Timestamp(ob["end"].iat[j]).tz_localize(None)
        assert all(not r["rule"].startswith("cadjpy")
                   for r in S.find_stories("EURUSD", h1, "D", {"cadjpy_exception": False}))
    assert n > 0


# ------------------------------------------------------------------ #30 targets, #31a overlap
def fake_set(X, levels, start_bar, end_bar):
    return S._LevelSet(pd.DataFrame({"start": [X.o_start[start_bar]], "end": [X.o_end[end_bar]]}), levels)


def test_target_uses_same_or_higher_tf_level():
    """story-line@648 / class-wrok@480-620: next opposite fresh KL of the same or a higher TF, the nearer one caps."""
    X = ctx(cad_days())
    t = X.o_end[8]
    base = X.target(False, 8, t, 1.0090)
    w = Level(1.0095, "sell", "A", 0)          # a fresh W sell level just above
    X.higher = [("W", fake_set(X, [w], 0, 4))]
    assert np.isclose(X.target(False, 8, t, 1.0090), 1.0095) and (base is None or base > 1.0095)
    X.cfg = {**X.cfg, "htf_targets": False}
    assert X.target(False, 8, t, 1.0090) == base  # origin TF only
    X.cfg = {**X.cfg, "htf_targets": True}
    X.higher = [("W", fake_set(X, [w], 0, 10))]   # W bar not closed at t: its levels are not known yet
    assert X.target(False, 8, t, 1.0090) == base


def test_overlap_needs_same_spot_and_closed_weekly_rejection():
    """all-in-1@1424-1620 + cadjpy-bd@811-905: same spot, fresh, the weekly tap judged after the weekly close."""
    X = ctx(cad_days())
    oc = [l for l in X.levels if l.kind == "OC" and l.side == "buy" and np.isclose(l.price, 1.004)][0]
    wl = Level(1.0041, "buy", "V", 0, [(0, "tap", True)])
    X.higher = [("W", fake_set(X, [wl], 0, 6))]   # the W candle holding day 5 closes at the end of day 6
    assert not X.overlap(oc, 5, X.o_end[5])        # weekly candle still open
    assert X.overlap(oc, 5, X.o_end[6])
    X.higher = [("W", fake_set(X, [Level(1.0080, "buy", "V", 0, [(0, "tap", True)])], 0, 6))]
    assert not X.overlap(oc, 5, X.o_end[6])        # not the same spot
    X.higher = [("W", fake_set(X, [wl], 0, 6))]
    X.cfg = {**X.cfg, "overlap_rule": False}
    assert not X.overlap(oc, 5, X.o_end[6])


def test_overlap_and_targets_on_walk():
    rows = [r for s in (1, 3) for r in S.find_stories("EURUSD", walk(24 * 900, s), "D")]
    assert any(r["rule"].endswith("+overlap") for r in rows)
    for r in rows:
        assert (r["target"] < r["entry_ref"]) if r["side"] == "SELL" else (r["target"] > r["entry_ref"])


# ------------------------------------------------------------------ #31b alignment
def test_breaks_from_structural_swings():
    c = [1, 2, 3, 2.5, 2.7, 2.4, 3.5, 3.2, 3.4, 3.0, 4.0, 3.6, 3.8, 3.1, 2.9, 3.3, 2.0, 2.5]
    br = S._breaks(structural_swings(c, pivots(c, 1)))
    assert br[-3:] == [(10, True, 3.0), (14, False, 4.0), (16, False, 3.3)]


def test_alignment_stories_on_walk():
    """weekly-recap@151-282: W BOS, then D BOS, then H4 BOS the same way; otherwise no continuation story."""
    n = 0
    for seed in (1, 3, 5):
        h1 = walk(24 * 900, seed)
        X = S._Ctx("EURUSD", h1, "D", S.DEFAULT)
        wbr = S._breaks(S._structure(X.hb, S.DEFAULT))
        w_end = X.hb["end"].to_numpy()
        h4 = S.resample(h1, "H4")
        close4 = dict(zip(h4["start"].astype(str).str[:16], h4["close"]))
        dbr = {i: (up, p) for i, up, p in S._breaks(S._structure(S.resample(h1, "D"), S.DEFAULT))}
        st = [str(x)[:16] for x in X.o_start]
        for r in S.find_stories("EURUSD", h1, "D"):
            if r["rule"] != "alignment":
                continue
            n += 1
            d = st.index(r["tap_time"])
            up = r["side"] == "BUY"
            assert d in dbr and dbr[d][0] == up and np.isclose(dbr[d][1], r["level"])   # D BOS that day
            w = [b for b in wbr if w_end[b[0]] <= X.o_start[d]][-1]
            assert w[1] == up                                                         # after a W BOS same way
            c = close4[r["breakout_time"]]
            assert (c > r["B"]) if up else (c < r["B"])                               # then the H4 break
            assert r["breakout_time"] >= str(X.o_end[d])[:16]
        assert all(r["rule"] != "alignment" for r in S.find_stories("EURUSD", h1, "D", {"alignment_start": False}))
    assert n > 0


# ------------------------------------------------------------------ v0.5 equivalence
def test_rules_off_equal_v05_engine():
    """With the v0.6 rules switched off the engine gives the v0.5 output (frozen golden), so every change in
    tests/golden/engine_golden.json comes from these rules."""
    off = {"most_recent_level": False, "flip_end": False, "htf_targets": False, "overlap_rule": False,
           "alignment_start": False, "cadjpy_exception": False}
    gold = json.load(open(G.PATH_V05))
    new = ("rule", "end_reason", "end_time", "next_day", "retrace", "level_time")
    for i in (0, 2, 3):
        pair, seed, hours, cfg = G.CASES[i]
        h1 = G.data(pair, seed, hours)
        for st in ("D", "W"):
            s = [{k: v for k, v in r.items() if k not in new} for r in S.find_stories(pair, h1, st, {**cfg, **off})]
            assert G._clean(s) == gold[i]["stories"][st], (i, st)
            cuts = list(range(len(h1) // 2, len(h1), max(1, len(h1) // 25)))[::5]
            t = [S.current_tap(pair, h1.iloc[:n], st, {**cfg, **off}) for n in cuts]
            t = [None if x is None else {k: v for k, v in x.items() if k not in new} for x in t]
            assert G._clean(t) == gold[i]["taps"][st][::5], (i, st)


# ------------------------------------------------------------------ live runner + Telegram
def test_live_rows_and_messages_show_rules():
    from datetime import datetime

    from slk.live import format_alert, pair_state, reconcile, summary_line, to_row
    base = {"pair": "EURUSD", "story": "D", "side": "BUY", "level_kind": "OC", "level": 1.004, "B": 1.004,
            "target": 1.012, "tap_time": "2023-01-09 22:00", "confirm_time": "2023-01-10 22:00", "rule": "cadjpy"}
    r = to_row(base, "CONFIRMED")
    assert r["rule"] == "cadjpy" and r["end_reason"] is None
    m = format_alert("CONFIRMED", r)
    assert "Rule: CADJPY exception" in m and "no H4 breakout needed" in m and "No point B" in m
    e = to_row({**base, "rule": "standard+overlap", "side": "SELL", "end_reason": "flip: D V level 1.0 rejected"},
               "ENDED_FLIP")
    m = format_alert("ENDED_FLIP", e)
    assert m.splitlines()[0] == "SELL \u00b7 EURUSD \u00b7 D1\u2192H4" and "Story over: ENDED EARLY (flip)" in m
    assert "Reason: flip: D V level" in m
    assert "overlap with W level" in m and "opposite story may start" in m
    assert "[alignment]" in summary_line("EURUSD", [{**r, "rule": "alignment"}])
    assert to_row({**base, "B": None}, "CONFIRMED")["point_b"] is None
    # an engine story that ended by a flip is stored ENDED_FLIP and announced
    old = {**r, "status": "CONFIRMED", "rule": "standard"}
    writes, alerts = reconcile([{**old, "status": "ENDED_FLIP", "end_reason": "flip"}], [old],
                               datetime(2023, 1, 20))
    assert [a for a, _ in alerts] == ["ENDED_FLIP"]
    h1 = walk(24 * 900, 1)
    rows = pair_state("EURUSD", h1, h1.index[-1] + pd.Timedelta(hours=1), ["D"], S.DEFAULT)
    assert "ENDED_FLIP" in {x["status"] for x in rows} and all(x.get("rule") for x in rows)
    assert all(x["end_reason"] for x in rows if x["status"] in ("ENDED_FLIP", "TARGET_HIT", "INVALIDATED"))
