"""cTrader client tests without network: framing, sizing, idempotency, safety, request/response loop."""
import socket
import threading

import pytest

from ctrader import sizing, tokens
from ctrader.client import CTraderClient, CTraderError, TradingRefused, find_existing_in, rows_to_frame, \
    trendbars_to_rows
from ctrader.framing import REGISTRY, common, decode_body, encode, model, oa, read_frame, split_frames


# ---------------------------------------------------------------- framing
def test_encode_decode_roundtrip():
    msg = oa.ProtoOANewOrderReq(ctidTraderAccountId=7, symbolId=1, orderType=model.MARKET, tradeSide=model.BUY,
                                volume=100000, relativeStopLoss=200, label="SLK", clientOrderId="slk-e1")
    frame = encode(msg, "abc")
    assert int.from_bytes(frame[:4], "big") == len(frame) - 4
    back, ptype, cid = decode_body(frame[4:])
    assert ptype == 2106 and cid == "abc"
    assert back == msg


def test_split_frames_partial_and_multiple():
    a = encode(common.ProtoHeartbeatEvent())
    b = encode(oa.ProtoOAVersionReq(), "x1")
    bodies, rest = split_frames(a + b[:5])
    assert len(bodies) == 1 and rest == b[:5]
    bodies, rest = split_frames(rest + b[5:])
    assert len(bodies) == 1 and rest == b""
    assert decode_body(bodies[0])[2] == "x1"


def test_registry_covers_core_messages():
    for cls in (oa.ProtoOAApplicationAuthRes, oa.ProtoOAExecutionEvent, oa.ProtoOAErrorRes, oa.ProtoOAGetTrendbarsRes,
                common.ProtoHeartbeatEvent, common.ProtoErrorRes):
        assert REGISTRY[cls().payloadType] is cls


def test_trendbars_to_frame():
    tb = model.ProtoOATrendbar(period=model.H1, low=108000, deltaOpen=10, deltaHigh=50, deltaClose=30,
                               utcTimestampInMinutes=27_000_000, volume=5)
    df = rows_to_frame(trendbars_to_rows([tb], 5))
    assert list(df.columns) == ["open", "high", "low", "close"]
    row = df.iloc[0]
    assert (row.open, row.high, row.low, row.close) == (1.0801, 1.0805, 1.08, 1.0803)
    assert str(df.index.tz) == "UTC" and df.index[0].timestamp() == 27_000_000 * 60


# ---------------------------------------------------------------- sizing
FX = dict(lot_size=10_000_000, min_volume=100_000, step_volume=100_000)  # 1 lot=100k units, min/step 0.01 lot


def test_pip_value_eurusd():
    assert sizing.pip_value_per_lot(4, 10_000_000) == pytest.approx(10.0)
    assert sizing.pip_value_per_lot(2, 10_000_000, quote_to_account=1 / 150) == pytest.approx(1000 / 150)


def test_volume_for_risk_basic_and_rounding():
    # 10k balance, 1% = 100 USD, 20 pips * 10 USD/pip/lot -> 0.5 lot
    assert sizing.volume_for_risk(10_000, 1.0, 20, 10.0, **FX) == 5_000_000
    # 0.37 lots -> rounds down to 0.37 exactly; 0.375 -> 0.37
    assert sizing.volume_for_risk(10_000, 0.75, 20, 10.0, **FX) == 3_700_000


def test_volume_for_risk_caps_and_min():
    assert sizing.volume_for_risk(1_000_000, 2, 10, 10.0, **FX, max_lots=1.5) == 15_000_000
    assert sizing.volume_for_risk(1_000_000, 2, 10, 10.0, **FX, max_volume=2_000_000) == 2_000_000
    assert sizing.volume_for_risk(50, 0.5, 30, 10.0, **FX) == 0  # below min volume -> skip
    assert sizing.volume_for_risk(10_000, 1, 0, 10.0, **FX) == 0


def test_relative_points_respects_digits():
    assert sizing.relative_points(1.10000, 1.09800, 5) == 200
    assert sizing.relative_points(150.000, 149.800, 3) == 20000
    assert sizing.relative_points(150.0004, 149.8, 3) % 100 == 0


# ---------------------------------------------------------------- idempotency
def test_client_order_id_deterministic():
    assert sizing.client_order_id(42) == sizing.client_order_id("42") == "slk-e42"
    assert sizing.client_order_id(42) != sizing.client_order_id(43)
    assert " " not in sizing.client_order_id("a b/c")
    with pytest.raises(ValueError):
        sizing.client_order_id("")


def test_find_existing_in():
    pos = [{"position_id": 1, "comment": "slk-e1", "label": "SLK"}]
    orders = [{"order_id": 9, "client_order_id": "slk-e2", "comment": "", "label": "SLK"}]
    assert find_existing_in(pos, orders, "slk-e1")["kind"] == "position"
    assert find_existing_in(pos, orders, "slk-e2")["order_id"] == 9
    assert find_existing_in(pos, orders, "slk-e3") is None


# ---------------------------------------------------------------- safety
def _client(env="demo", **settings):
    return CTraderClient(env=env, client_id="x", client_secret="y", settings=tokens.MemorySettings(settings))


def test_kill_switch_refuses_opening_but_not_closing():
    c = _client(kill_switch="on")
    with pytest.raises(TradingRefused):
        c.check_can_trade()
    c.check_can_trade(opening=False)
    with pytest.raises(TradingRefused):
        c.place_market_order("EURUSD", "BUY", 100000, client_order_id="slk-e1")  # refused before any I/O


def test_live_requires_allow_live():
    c = _client(env="live")
    with pytest.raises(TradingRefused):
        c.check_can_trade()
    c.check_can_trade(allow_live=True)
    _client(env="demo").check_can_trade()


def test_token_refresh_stores_settings():
    s = tokens.MemorySettings({"ctrader_refresh_token": "old"})
    seen = {}

    def fake_get(url, params):
        seen.update(params)
        return {"accessToken": "A2", "refreshToken": "R2", "expiresIn": 2_628_000, "tokenType": "bearer"}

    t = tokens.refresh_tokens(s, client_id="c", client_secret="s", http_get=fake_get)
    assert seen["grant_type"] == "refresh_token" and seen["refresh_token"] == "old"
    assert s.get("ctrader_access_token") == "A2" and s.get("ctrader_refresh_token") == "R2"
    assert float(s.get("ctrader_token_expiry")) == t["expiry"]
    assert not tokens.needs_refresh(t)
    assert tokens.needs_refresh({"expiry": t["expiry"] - 2_628_000 + 3600})


# ---------------------------------------------------------------- request loop over a local socket pair
def _fake_server(sock, handler):
    def run():
        try:
            while True:
                msg, ptype, cid = decode_body(read_frame(sock))
                for reply in handler(msg) or []:
                    sock.sendall(encode(reply, cid))
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def test_request_roundtrip_and_error():
    a, b = socket.socketpair()

    def handler(msg):
        if isinstance(msg, oa.ProtoOAApplicationAuthReq):
            if msg.clientSecret == "bad":
                return [oa.ProtoOAErrorRes(errorCode="CH_CLIENT_AUTH_FAILURE", description="nope")]
            return [common.ProtoHeartbeatEvent(), oa.ProtoOAApplicationAuthRes()]
        return []

    _fake_server(b, handler)
    c = _client()
    c._sock = a
    for fn in (c._reader,):
        threading.Thread(target=fn, daemon=True).start()
    c.app_auth()
    c.client_secret = "bad"
    with pytest.raises(CTraderError) as e:
        c.app_auth()
    assert e.value.code == "CH_CLIENT_AUTH_FAILURE"
    c.close()
    b.close()
