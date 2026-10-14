"""Gold alert check (REVIEW "Gold alert check", 2026-10-14): cTrader error replies that used to time out, symbol
candidates, per-symbol pip size / price format (metals, indices), Dukascopy scale, and point B on the owner's
XAUUSD H4 close line."""
import socket
import threading
import time

import numpy as np
import pandas as pd
import pytest

from ctrader import client as cmod
from ctrader import tokens
from ctrader.client import CTraderClient, CTraderError
from ctrader.framing import common, decode_body, encode, model, oa, read_frame
from slk import data, instruments, store
from slk.structure import SwingBook, pivots
from slk.story import _point_b, pip

SAME = object()  # reply carries the request's clientMsgId


@pytest.fixture(autouse=True)
def _clean_registry():
    instruments.clear()
    yield
    instruments.clear()


def _serve(sock, handler):
    """Fake cTrader server: handler(msg) -> [(reply, cid)] with cid SAME (the request's), None or any text."""
    def run():
        try:
            while True:
                msg, _, cid = decode_body(read_frame(sock))
                for reply, rc in handler(msg) or []:
                    sock.sendall(encode(reply, cid if rc is SAME else rc))
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def _client(handler, timeout=3.0):
    a, b = socket.socketpair()
    _serve(b, handler)
    c = CTraderClient(env="demo", client_id="x", client_secret="y", settings=tokens.MemorySettings(), timeout=timeout)
    c._sock = a
    threading.Thread(target=c._reader, daemon=True).start()
    c.account_id = 1
    return c, b


def _tb(t, low=415000000):
    return model.ProtoOATrendbar(period=model.H1, low=low, deltaOpen=1000, deltaHigh=5000, deltaClose=3000,
                                 utcTimestampInMinutes=t // 60, volume=7)


def _symbols(*named):
    """SymbolsList + SymbolById replies for [(id, name)] (gold-like: digits 2, pipPosition 1)."""
    def handle(msg):
        if isinstance(msg, oa.ProtoOASymbolsListReq):
            return [(oa.ProtoOASymbolsListRes(ctidTraderAccountId=1, symbol=[
                model.ProtoOALightSymbol(symbolId=i, symbolName=n, enabled=True) for i, n in named]), SAME)]
        if isinstance(msg, oa.ProtoOASymbolByIdReq):
            return [(oa.ProtoOASymbolByIdRes(ctidTraderAccountId=1, symbol=[
                model.ProtoOASymbol(symbolId=i, digits=2, pipPosition=1, lotSize=100, minVolume=100, stepVolume=100)
                for i in msg.symbolId]), SAME)]
        if isinstance(msg, oa.ProtoOAVersionReq):
            return [(oa.ProtoOAVersionRes(version="99"), SAME)]
        return None
    return handle


# ---------------------------------------------------------------- error replies surface instead of timing out
@pytest.mark.parametrize("cid", [None, "someone-else"])
def test_trendbar_error_without_our_cid_is_raised_not_a_timeout(cid):
    def handler(msg):
        if isinstance(msg, oa.ProtoOAGetTrendbarsReq):
            return [(oa.ProtoOAErrorRes(ctidTraderAccountId=1, errorCode="SYMBOL_NOT_FOUND",
                                        description="no history"), cid)]
        return _symbols((41, "XAUUSD"))(msg)

    c, b = _client(handler, timeout=5.0)
    t0 = time.monotonic()
    with pytest.raises(CTraderError) as e:
        c.get_trendbars("XAUUSD", "H1", pd.Timestamp("2026-10-07", tz="UTC"), pd.Timestamp("2026-10-14", tz="UTC"))
    assert e.value.code == "SYMBOL_NOT_FOUND"
    assert time.monotonic() - t0 < 3  # answered at once, not after the 5 s timeout
    c.close()
    b.close()


def test_account_disconnect_event_ends_the_request():
    def handler(msg):
        if isinstance(msg, oa.ProtoOAGetTrendbarsReq):
            return [(oa.ProtoOAAccountDisconnectEvent(ctidTraderAccountId=1), None)]
        return _symbols((41, "XAUUSD"))(msg)

    c, b = _client(handler)
    with pytest.raises(CTraderError) as e:
        c.trendbar_rows("XAUUSD", "H1", 1_791_000_000, 1_791_100_000)
    assert e.value.code == "ACCOUNT_DISCONNECTED"
    c.close()
    b.close()


def test_timeout_says_what_the_server_sent_meanwhile():
    def handler(msg):
        if isinstance(msg, oa.ProtoOATraderReq):
            return [(oa.ProtoOASpotEvent(ctidTraderAccountId=1, symbolId=41, bid=415000000), None)]
        return None

    c, b = _client(handler, timeout=0.4)
    with pytest.raises(TimeoutError) as e:
        c.request(oa.ProtoOATraderReq(ctidTraderAccountId=1))
    assert "ProtoOATraderReq" in str(e.value) and "ProtoOASpotEvent (no cid)" in str(e.value)
    c.close()
    b.close()


def test_late_error_of_a_timed_out_request_is_not_blamed_on_the_next_one():
    state = {"n": 0, "first": None}

    def handler(msg):
        state["n"] += 1
        if state["n"] == 1:
            return None  # first request: no reply in time
        return [(oa.ProtoOAErrorRes(errorCode="LATE", description="for the first"), state["first"]),
                (oa.ProtoOAVersionRes(version="1"), SAME)]

    c, b = _client(handler, timeout=0.3)
    orig = c._send

    def send(msg, cid=None):
        if state["first"] is None:
            state["first"] = cid
        return orig(msg, cid)

    c._send = send
    with pytest.raises(TimeoutError):
        c.request(oa.ProtoOAVersionReq())
    assert c.request(oa.ProtoOAVersionReq(), timeout=2).version == "1"
    c.close()
    b.close()


# ---------------------------------------------------------------- symbol candidates
def test_exact_symbol_name_wins_and_ignored_id_falls_over_to_the_next(monkeypatch):
    monkeypatch.setattr(cmod, "HIST_MIN_GAP_S", 0.0)
    asked = []
    lo = int(pd.Timestamp("2026-10-12", tz="UTC").timestamp())

    def handler(msg):
        if isinstance(msg, oa.ProtoOAGetTrendbarsReq):
            asked.append(msg.symbolId)
            if msg.symbolId == 41:
                return None  # the server ignores this one
            return [(oa.ProtoOAGetTrendbarsRes(ctidTraderAccountId=1, period=model.H1, symbolId=msg.symbolId,
                                               timestamp=0, trendbar=[_tb(lo), _tb(lo + 3600)]), SAME)]
        return _symbols((77, "XAU/USD"), (41, "XAUUSD"))(msg)

    c, b = _client(handler, timeout=0.5)
    info = c.symbol("XAUUSD")
    assert info["symbol_id"] == 41 and info["candidates"] == [41, 77]
    rows = c.trendbar_rows("XAUUSD", "H1", lo, lo + 7200)
    assert asked == [41, 77] and [r[0] for r in rows] == [lo, lo + 3600]
    assert rows[0][1:5] == (4150.01, 4150.05, 4150.0, 4150.03)  # 1/100000 units, rounded to digits 2
    c.close()
    b.close()


def test_ignored_trendbars_on_a_live_link_raise_with_diagnostics(monkeypatch):
    monkeypatch.setattr(cmod, "HIST_MIN_GAP_S", 0.0)

    def handler(msg):
        if isinstance(msg, oa.ProtoOAGetTrendbarsReq):
            return None
        return _symbols((41, "XAUUSD"))(msg)

    c, b = _client(handler, timeout=0.3)
    with pytest.raises(CTraderError) as e:
        c.trendbar_rows("XAUUSD", "H1", 1_791_000_000, 1_791_100_000)
    assert e.value.code == "NO_TRENDBARS_REPLY"
    assert "symbolId 41" in e.value.description and "ping ok" in e.value.description
    assert "pipPosition 1" in e.value.description
    c.close()
    b.close()


def test_registry_has_no_unknown_error_types():
    assert cmod._ERRORS[0] is oa.ProtoOAErrorRes and common.ProtoErrorRes in cmod._ERRORS


# ---------------------------------------------------------------- pip size, decimals, Dukascopy scale
def test_pip_sizes_and_formatting():
    assert pip("EURUSD") == 0.0001 and pip("USDJPY") == 0.01
    assert pip("XAUUSD") == 0.1 and pip("XAGUSD") == 0.01 and pip("US500") == 1.0 and pip("DE40") == 1.0
    from slk.live import fmt_price
    assert fmt_price("XAUUSD", 4154.36) == "4154.36"
    assert fmt_price("XAGUSD", 48.1234) == "48.123"
    assert fmt_price("EURUSD", 1.1) == "1.10000" and fmt_price("GBPJPY", 200.1) == "200.100"
    assert fmt_price("US500", 6700.5) == "6700.50" and fmt_price("XAUUSD", None) == "-"


def test_ctrader_pip_position_preferred_when_known():
    assert instruments.mismatch("XAUUSD", 1) is None
    instruments.register("XAUUSD", pip_position=2, digits=2)
    assert pip("XAUUSD") == 0.01  # the broker's own pip wins over the table
    assert "pipPosition 2" in instruments.mismatch("XAUUSD", 2)
    instruments.clear()
    assert pip("XAUUSD") == 0.1


def test_store_keeps_symbol_info_and_registers_it(tmp_path):
    root = str(tmp_path)
    p = store.Pair("XAUUSD", root, source="ctrader")
    p.put([(1_791_000_000, 4150.0, 4151.0, 4149.0, 4150.5)], store.CUR)
    p.sym = {"symbol_id": 41, "name": "XAUUSD", "digits": 2, "pip_position": 1}
    p.save()
    instruments.clear()
    q = store.Pair("XAUUSD", root)
    assert q.sym["pip_position"] == 1 and pip("XAUUSD") == 0.1 and instruments.decimals("XAUUSD") == 2


def test_dukascopy_scale_and_names():
    assert data.point("XAUUSD") == 1e3 and data.point("XAGUSD") == 1e3
    assert data.point("EURUSD") == 1e5 and data.point("CADJPY") == 1e3
    assert data._name("US500") == "USA500IDXUSD" and data._name("XAUUSD") == "XAUUSD"


def test_gold_tolerances_scale_with_pip():
    from slk.levels import touch_tol
    from slk.story import DEFAULT
    assert touch_tol({**DEFAULT, "level_tol_pips": 2.0}, pip("XAUUSD")) == pytest.approx(0.2)
    assert DEFAULT["stop_buffer_pips"] * pip("XAUUSD") == pytest.approx(0.2)  # was 0.0002 (0.0001 pip)


def test_gold_alert_prices():
    from slk.live import format_alert
    r = {"pair": "XAUUSD", "story": "D", "side": "BUY", "level_kind": "flip", "level": 4154.36, "point_b": 4161.03,
         "target": 4175.6, "invalidation": 4154.36, "tap_time": "2026-10-12 22:00", "level_time": "2026-10-08 22:00",
         "rule": "standard", "trend": "up", "htf_trend": "up"}
    text = format_alert("TAPPED", r)
    assert "@ 4154.36 " in text and "Point B 4161.03" in text and "4154.36000" not in text


# ---------------------------------------------------------------- point B on the owner's H4 close line
# Owner's IC chart (Oct 12-13 2026): closes ~4191, 4186, 4172, 4150, 4161.03 (green; next red candle opens there =
# A-shape on the close line), 4156, 4150, 4141, then the tap of the D level.
GOLD_H4 = [4191.0, 4186.0, 4172.0, 4150.0, 4161.03, 4156.0, 4150.0, 4141.0, 4138.0, 4152.0]


def test_point_b_is_the_last_h4_a_shape_before_the_first_touch():
    piv = pivots(GOLD_H4, 1)  # b_pivot = 1
    book = SwingBook(piv)
    k0 = 8  # first H4 bar touching the D level (the level lies below the 4141 close)
    assert _point_b(book.at(k0), k0, sell=False) == 4161.03
    assert [p[2] for p in piv if p[1] == "H"] == [4161.03]


def test_point_b_moves_back_when_the_level_was_already_touched_before_the_a_shape():
    """With the D level at 4154.36 the H4 bar closing at 4150 already traded through it: that is the FIRST touch.
    The 4161.03 A-shape comes after it, so the rule ("last A before the first tap") cannot take it and reaches back
    to the last turn before the drop. On a feed where the H4 closes before the drop dip by a hair (4170.20 then
    4171.50, Dukascopy-like) that turn is a 4171.50 order-1 A-shape = the B in the live alert."""
    closes = [4191.0, 4186.0, 4170.2, 4171.5, 4150.0, 4161.03, 4156.0, 4150.0, 4141.0]
    book = SwingBook(pivots(closes, 1))
    k0 = 4  # bar closing 4150: its wick reached 4154.36
    assert _point_b(book.at(k0), k0, sell=False) == 4171.5
    k_late = 8  # had the first touch come after the A-shape, B would be the owner's 4161.03
    assert _point_b(book.at(k_late), k_late, sell=False) == 4161.03


def test_h4_grid_matches_ic_server_time():
    """Our H4 = 17:00 New York based (21:00/01:00/05:00... UTC in summer); IC Markets server time is GMT+3 in summer
    (00:00 server = 17:00 NY), so its H4 candles start at the same instants (22:00/02:00/06:00... WAT)."""
    from slk.candles import resample
    idx = pd.date_range("2026-10-12 21:00", "2026-10-14 21:00", freq="h", tz="UTC", inclusive="left")
    h1 = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)
    h4 = resample(h1, "H4")
    hours = sorted(set(pd.to_datetime(h4["start"]).dt.hour))
    assert hours == [1, 5, 9, 13, 17, 21]
    server = pd.to_datetime(h4["start"]) + pd.Timedelta(hours=3)
    assert set(server.dt.hour) == {0, 4, 8, 12, 16, 20}


# ---------------------------------------------------------------- debug-pair export + explanation
def _gold_walk():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2025-06-01", "2026-10-14", freq="h", tz="UTC")
    idx = idx[~store._closed_mask(idx.asi8 // 10**9)]
    c = 3300 + np.cumsum(rng.normal(0, 4, len(idx)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + rng.uniform(0, 3, len(c)),
                         "low": np.minimum(o, c) - rng.uniform(0, 3, len(c)), "close": c}, index=idx)


def test_debug_pair_exports_and_explains_point_b(monkeypatch, tmp_path, capsys):
    from slk import debug_pair
    h1 = _gold_walk()
    monkeypatch.setattr(debug_pair, "fetch", lambda pair, days: (h1, "dukascopy", "NO_TRENDBARS_REPLY: test"))
    assert debug_pair.main(["--pair", "xauusd", "--days", "500", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "XAUUSD_H1_dukascopy.csv.gz").exists()
    text = (tmp_path / "XAUUSD_explain.txt").read_text()
    assert "pip 0.1" in text and "(k0)" in text and "point B = " in text and "cTrader error: NO_TRENDBARS" in text
    out = capsys.readouterr().out
    assert "::notice title=XAUUSD candles::" in out and "source dukascopy" in out
