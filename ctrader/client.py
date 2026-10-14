"""Minimal synchronous cTrader Open API client (TLS + protobuf), for short-lived jobs.

Why not the `ctrader-open-api` PyPI package: it is a Twisted reactor client (callbacks, reactor that
cannot be restarted in one process) and pins old versions (protobuf==3.20.1, requests==2.32.3,
Twisted==24.3.0). We reuse its generated protobuf modules (vendored in ctrader/messages, MIT) and do
the transport ourselves: one reader thread, one heartbeat thread (every 10 s), blocking request().

Usage:
    with CTraderClient() as c:          # connects, app auth, account auth (refreshes token if needed)
        print(c.get_trader()["balance"])
        df = c.get_trendbars("EURUSD", "H1", start, end)
"""
import os
import socket
import ssl
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone

from ctrader import sizing, tokens
from ctrader.framing import REGISTRY, common, decode_body, encode, model, oa, read_frame

HOSTS = {"demo": "demo.ctraderapi.com", "live": "live.ctraderapi.com"}
PORT = 5035
HEARTBEAT_S = 10

# Largest request window per trendbar period that Spotware accepts (ProtoOAGetTrendbarsReq docs: M1-M5 5 weeks,
# M10-H1 35 weeks, H4-D1 1 year, W1/MN1 5 years). get_trendbars / trendbar_rows split longer ranges into such chunks
# and halve a chunk if the server still answers INCORRECT_BOUNDARIES.
_WEEK = timedelta(weeks=1)
_CHUNK = {"M1": 5 * _WEEK, "M2": 5 * _WEEK, "M3": 5 * _WEEK, "M4": 5 * _WEEK, "M5": 5 * _WEEK,
          "M10": 35 * _WEEK, "M15": 35 * _WEEK, "M30": 35 * _WEEK, "H1": 35 * _WEEK,
          "H4": timedelta(days=366), "H12": timedelta(days=366), "D1": timedelta(days=366),
          "W1": timedelta(days=1830), "MN1": timedelta(days=1830)}
# Historical-data requests (trendbars, ticks) are limited to 5 per second per connection: keep a gap between them
# and retry with backoff when the server answers REQUEST_FREQUENCY_EXCEEDED.
HIST_MIN_GAP_S = 0.25
HIST_RETRIES = 6
_GAP_S = 4 * 86400  # a hole longer than this inside a reply (FX weekend + holiday < 4 days) = truncated reply


class CTraderError(Exception):
    def __init__(self, code, description=""):
        super().__init__(f"{code}: {description}")
        self.code, self.description = code, description


# Replies that answer (or kill) a pending request even when they do not carry its clientMsgId: an error without
# clientMsgId, or the server dropping the account / the app / the token. Before 2026-10-14 `request` waited only for
# its own clientMsgId, so such a reply made it time out ("no response from cTrader") instead of raising the error.
_ERRORS = (oa.ProtoOAErrorRes, common.ProtoErrorRes, oa.ProtoOAOrderErrorEvent)
_FATAL = (oa.ProtoOAAccountDisconnectEvent, oa.ProtoOAClientDisconnectEvent, oa.ProtoOAAccountsTokenInvalidatedEvent)
_NAMES = {k: v.__name__ for k, v in REGISTRY.items()}


def _describe(msg, ptype, cid):
    """'ProtoOAErrorRes cid=ab12 CH_SYMBOL_NOT_FOUND: text' for diagnostics (no secrets: ids and codes only)."""
    s = _NAMES.get(ptype, f"payloadType {ptype}") + (f" cid={cid}" if cid else " (no cid)")
    if msg is not None and hasattr(msg, "errorCode") and msg.HasField("errorCode"):
        s += f" {msg.errorCode}"
        if hasattr(msg, "description") and msg.description:
            s += f": {msg.description[:120]}"
    if isinstance(msg, oa.ProtoOAClientDisconnectEvent) or isinstance(msg, oa.ProtoOAAccountsTokenInvalidatedEvent):
        s += f" reason={msg.reason[:120]}"
    return s


def _fields(msg):
    """' (symbolId 41, H1, 2026-10-07T12:00..2026-10-14T12:00)' for the request fields that matter in a trendbar /
    symbol request (diagnostics)."""
    out = []
    names = msg.DESCRIPTOR.fields_by_name
    if "symbolId" in names:
        v = msg.symbolId
        out.append(f"symbolId {list(v) if not isinstance(v, int) else v}")
    if "period" in names and msg.HasField("period"):
        out.append(model.ProtoOATrendbarPeriod.Name(msg.period))
    if "fromTimestamp" in names and msg.HasField("fromTimestamp"):
        iso = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M")  # noqa: E731
        out.append(f"{iso(msg.fromTimestamp)}..{iso(msg.toTimestamp)}")
    return f" ({', '.join(out)})" if out else ""


def _fatal_error(msg):
    """CTraderError for a server event that ends every pending request (account/app disconnected, token gone)."""
    if isinstance(msg, oa.ProtoOAAccountDisconnectEvent):
        return CTraderError("ACCOUNT_DISCONNECTED", "server disconnected the trading account (re-auth needed)")
    if isinstance(msg, oa.ProtoOAClientDisconnectEvent):
        return CTraderError("CLIENT_DISCONNECTED", msg.reason)
    return CTraderError("ACCESS_TOKEN_INVALIDATED", msg.reason)


class TradingRefused(Exception):
    """Raised before anything is sent when a safety rule blocks trading."""


def _ms(t):
    if isinstance(t, (int, float)):
        return int(t * 1000) if t < 1e11 else int(t)
    if isinstance(t, str):
        t = datetime.fromisoformat(t)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return int(t.timestamp() * 1000)


def _norm(name):
    return "".join(ch for ch in str(name).upper() if ch.isalnum())


class CTraderClient:
    def __init__(self, env=None, client_id=None, client_secret=None, account_id=None, settings=None,
                 timeout=20.0, connect_timeout=15.0):
        self.env = (env or os.environ.get("CTRADER_ENV") or "demo").lower()
        if self.env not in HOSTS:
            raise ValueError(f"CTRADER_ENV must be demo or live, got {self.env!r}")
        self.client_id = client_id or os.environ.get("CTRADER_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("CTRADER_CLIENT_SECRET")
        self.account_id_cfg = account_id or os.environ.get("CTRADER_ACCOUNT_ID")
        self.settings = settings if settings is not None else tokens.default_settings()
        self.timeout, self.connect_timeout = timeout, connect_timeout
        self.account_id = None  # ctidTraderAccountId after account_auth
        self.account_is_live = None
        self._sock = None
        self._send_lock = threading.Lock()
        self._cond = threading.Condition()
        self._inbox = []
        self._dead = None
        self._stop = threading.Event()
        self._threads = []
        self._hist_lock = threading.Lock()
        self._hist_last = 0.0
        self._symbols = {}       # normalized name -> info dict
        self._symbol_names = {}  # symbolId -> name
        self._pending = set()    # clientMsgIds of requests still waiting for their reply
        self._abandoned = deque(maxlen=200)  # clientMsgIds of requests that timed out (late replies are ignored)
        self._recent = deque(maxlen=80)  # (monotonic time, description) of every non-heartbeat message: diagnostics

    # ---------------------------------------------------------------- transport
    def connect(self):
        host = HOSTS[self.env]
        raw = socket.create_connection((host, PORT), timeout=self.connect_timeout)
        self._sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        self._sock.settimeout(None)
        self._stop.clear()
        self._dead = None
        for fn in (self._reader, self._heartbeat):
            th = threading.Thread(target=fn, daemon=True)
            th.start()
            self._threads.append(th)
        return self

    def close(self):
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._sock.close()
            self._sock = None

    def __enter__(self):
        self.connect()
        self.app_auth()
        self.account_auth()
        return self

    def __exit__(self, *exc):
        self.close()

    def _send(self, msg, cid=None):
        data = encode(msg, cid)
        with self._send_lock:
            if self._sock is None:
                raise ConnectionError("not connected")
            self._sock.sendall(data)

    def _reader(self):
        try:
            while not self._stop.is_set():
                msg, ptype, cid = decode_body(read_frame(self._sock))
                if ptype == common.ProtoHeartbeatEvent().payloadType:
                    continue
                self._recent.append((time.monotonic(), _describe(msg, ptype, cid)))
                with self._cond:
                    self._inbox.append((msg, ptype, cid))
                    if len(self._inbox) > 2000:
                        del self._inbox[:500]
                    self._cond.notify_all()
        except Exception as e:  # socket closed or broken
            with self._cond:
                self._dead = e
                self._cond.notify_all()

    def _heartbeat(self):
        while not self._stop.wait(HEARTBEAT_S):
            try:
                self._send(common.ProtoHeartbeatEvent())
            except Exception:
                return

    def _wait(self, pred, timeout=None):
        deadline = time.monotonic() + (timeout or self.timeout)
        with self._cond:
            while True:
                for i, item in enumerate(self._inbox):
                    if pred(*item):
                        del self._inbox[i]
                        return item[0]
                if self._dead is not None and not self._stop.is_set():
                    raise ConnectionError(f"connection lost: {self._dead}")
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("no response from cTrader")
                self._cond.wait(left)

    @staticmethod
    def _raise_if_error(msg):
        if isinstance(msg, (oa.ProtoOAErrorRes, common.ProtoErrorRes)):
            raise CTraderError(msg.errorCode, msg.description)
        if isinstance(msg, oa.ProtoOAOrderErrorEvent):
            raise CTraderError(msg.errorCode, msg.description)

    def _orphan(self, m, c):
        """An error / disconnect event that belongs to no other pending request: it answers the waiting one."""
        if isinstance(m, _FATAL):
            return True
        return isinstance(m, _ERRORS) and (c is None or (c not in self._pending and c not in self._abandoned))

    def request(self, msg, timeout=None, pred=None):
        """Send msg and return the first reply carrying our clientMsgId (or matching pred). An error reply without
        a clientMsgId (or with one no pending request owns) and an account/app/token disconnect event are raised as
        CTraderError instead of waiting for the timeout; a timeout says what the server did send meanwhile."""
        cid = uuid.uuid4().hex[:16]
        base = pred(cid) if pred else (lambda m, t, c: c == cid)
        t0 = time.monotonic()
        with self._cond:
            self._pending.add(cid)
        try:
            self._send(msg, cid)
            reply = self._wait(lambda m, t, c: base(m, t, c) or self._orphan(m, c), timeout)
        except TimeoutError:
            self._abandoned.append(cid)
            raise TimeoutError(f"no response from cTrader to {type(msg).__name__}{_fields(msg)} within "
                               f"{timeout or self.timeout:.0f}s; {self._since(t0)}") from None
        finally:
            with self._cond:
                self._pending.discard(cid)
        if isinstance(reply, _FATAL):
            raise _fatal_error(reply)
        self._raise_if_error(reply)
        return reply

    def _since(self, t0):
        seen = [d for t, d in list(self._recent) if t >= t0]
        if not seen:
            return "nothing else received meanwhile"
        return f"received meanwhile ({len(seen)}): " + "; ".join(seen[-8:])

    def ping(self, timeout=10):
        """True when the connection still answers (ProtoOAVersionReq): tells a dead link from an ignored request."""
        try:
            self.request(oa.ProtoOAVersionReq(), timeout=timeout)
            return True
        except Exception:
            return False

    # ---------------------------------------------------------------- auth
    def app_auth(self):
        if not (self.client_id and self.client_secret):
            raise RuntimeError("CTRADER_CLIENT_ID / CTRADER_CLIENT_SECRET not set")
        self.request(oa.ProtoOAApplicationAuthReq(clientId=self.client_id, clientSecret=self.client_secret))

    def get_accounts(self, access_token=None):
        """Accounts the token can trade: [{ctid, is_live, login}]."""
        tok = access_token or tokens.load_tokens(self.settings)["access_token"]
        r = self.request(oa.ProtoOAGetAccountListByAccessTokenReq(accessToken=tok))
        return [{"ctid": a.ctidTraderAccountId, "is_live": a.isLive, "login": a.traderLogin}
                for a in r.ctidTraderAccount]

    def account_auth(self):
        tk = tokens.load_tokens(self.settings)
        if tokens.needs_refresh(tk):
            tk = self._refresh()
        if not tk["access_token"]:
            raise RuntimeError("no access token (CTRADER_ACCESS_TOKEN / settings.ctrader_access_token)")
        try:
            self._account_auth(tk["access_token"])
        except CTraderError as e:
            if "TOKEN" not in str(e.code).upper() or not tk.get("refresh_token"):
                raise
            tk = self._refresh()
            self._account_auth(tk["access_token"])

    def _refresh(self):
        return tokens.refresh_tokens(self.settings, client_id=self.client_id, client_secret=self.client_secret)

    def _account_auth(self, access_token):
        accounts = self.get_accounts(access_token)
        want = str(self.account_id_cfg or "").strip()
        acc = None
        for a in accounts:
            if want and want in (str(a["ctid"]), str(a["login"])):
                acc = a
        if acc is None and not want and len(accounts) == 1:
            acc = accounts[0]
        if acc is None:
            raise RuntimeError(f"CTRADER_ACCOUNT_ID {want or '(unset)'} not among the token's accounts "
                               f"(accounts: {[(a['login'], 'live' if a['is_live'] else 'demo') for a in accounts]}; "
                               f"the secret has {len(want)} characters, digits only: {want.isdigit()})")
        if acc["is_live"] != (self.env == "live"):
            raise RuntimeError(f"account {acc['login']} is {'live' if acc['is_live'] else 'demo'} "
                               f"but CTRADER_ENV={self.env}")
        self.request(oa.ProtoOAAccountAuthReq(ctidTraderAccountId=acc["ctid"], accessToken=access_token))
        self.account_id, self.account_is_live = acc["ctid"], acc["is_live"]

    # ---------------------------------------------------------------- account / market data
    def get_trader(self):
        t = self.request(oa.ProtoOATraderReq(ctidTraderAccountId=self.account_id)).trader
        digits = t.moneyDigits if t.HasField("moneyDigits") else 2
        return {"balance": t.balance / 10 ** digits, "login": t.traderLogin, "broker": t.brokerName,
                "leverage": t.leverageInCents / 100, "deposit_asset_id": t.depositAssetId, "money_digits": digits}

    def get_symbols(self, names=None):
        """name -> {symbol_id, name, digits, pip_position, lot_size, min_volume, max_volume, step_volume,
        candidates}. `names` limits the detail request to those symbols (faster).
        Several broker symbols can normalise to one name (e.g. 'XAUUSD' and 'XAU/USD' or 'XAUUSD.'): the one whose
        name is exactly the requested one wins, else the lowest id; `candidates` lists all their ids (exact name
        first), tried in turn by trendbar_rows when the server ignores a trendbar request for one of them."""
        light = self.request(oa.ProtoOASymbolsListReq(ctidTraderAccountId=self.account_id)).symbol
        by_id = {s.symbolId: s.symbolName for s in light if s.enabled}
        if names:
            wanted = {_norm(n) for n in names}
            by_id = {i: n for i, n in by_id.items() if _norm(n) in wanted}
        ids = list(by_id)
        out, groups = {}, {}
        for k in range(0, len(ids), 100):
            r = self.request(oa.ProtoOASymbolByIdReq(ctidTraderAccountId=self.account_id, symbolId=ids[k:k + 100]))
            for s in r.symbol:
                name = by_id[s.symbolId]
                info = {"symbol_id": s.symbolId, "name": name, "digits": s.digits, "pip_position": s.pipPosition,
                        "lot_size": s.lotSize, "min_volume": s.minVolume, "max_volume": s.maxVolume,
                        "step_volume": s.stepVolume}
                out[name] = info
                groups.setdefault(_norm(name), []).append(info)
                self._symbol_names[s.symbolId] = name
        for key, infos in groups.items():
            infos.sort(key=lambda i: (i["name"].upper() != key, i["symbol_id"]))
            best = infos[0]
            best["candidates"] = [i["symbol_id"] for i in infos]
            self._symbols[key] = best
        return out

    def symbol(self, name):
        key = _norm(name)
        if key not in self._symbols:
            self.get_symbols([name])
        if key not in self._symbols:
            raise KeyError(f"symbol {name} not found on this account")
        return self._symbols[key]

    def get_trendbars(self, symbol, period="H1", start=None, end=None):
        """OHLC DataFrame (UTC index 't', columns open/high/low/close, bid prices) like slk.data.hourly."""
        end = end or datetime.now(timezone.utc)
        start = start or (datetime.now(timezone.utc) - timedelta(days=7))
        return rows_to_frame([r[:5] for r in self.trendbar_rows(symbol, period, start, end)])

    def max_span(self, period="H1"):
        """Largest window (seconds) one trendbar request may cover."""
        return int(_CHUNK.get(period, timedelta(days=30)).total_seconds())

    def _hist_request(self, msg):
        """A historical-data request under Spotware's limit (5/s): spaced HIST_MIN_GAP_S apart, retried with
        backoff on REQUEST_FREQUENCY_EXCEEDED."""
        for attempt in range(HIST_RETRIES):
            with self._hist_lock:
                wait = self._hist_last + HIST_MIN_GAP_S - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._hist_last = time.monotonic()
            try:
                return self.request(msg)
            except CTraderError as e:
                if str(e.code) != "REQUEST_FREQUENCY_EXCEEDED" or attempt == HIST_RETRIES - 1:
                    raise
                time.sleep(min(2 ** attempt, 16))

    def trendbar_rows(self, symbol, period="H1", start=None, end=None):
        """Bars with open time in [start, end) as rows (t UTC seconds, open, high, low, close, volume), sorted.
        Uses the largest window per request the API allows (_CHUNK); a reply that leaves a hole of more than
        4 days at either end of its window (a server-side bar cap) is completed by more requests."""
        info = self.symbol(symbol)
        ids = list(info.get("candidates") or [info["symbol_id"]])
        lo_all = _ms(start) // 1000
        hi_all = _ms(end or datetime.now(timezone.utc)) // 1000
        span = self.max_span(period)
        pe = model.ProtoOATrendbarPeriod.Value(period)
        got = {}
        todo = []
        b = hi_all
        while b > lo_all:  # newest chunk first
            a = max(lo_all, b - span)
            todo.append((a, b))
            b = a
        todo.reverse()
        n = 0
        while todo:
            a, b = todo.pop()
            n += 1
            if n > 20000:
                raise RuntimeError("trendbar_rows: too many requests")
            try:
                r = self._hist_request(oa.ProtoOAGetTrendbarsReq(
                    ctidTraderAccountId=self.account_id, symbolId=ids[0], period=pe,
                    fromTimestamp=a * 1000, toTimestamp=b * 1000))
            except TimeoutError as e:
                # The server ignored the request. A dead link -> ConnectionError (the store reconnects once); a live
                # link -> try the next broker symbol of that name, else raise with what we know.
                alive = self.ping()
                if not alive:
                    raise ConnectionError(f"{e}; connection dead after it") from None
                if len(ids) > 1:
                    print(f"{symbol}: no trendbars for symbolId {ids[0]}, trying {ids[1]}", flush=True)
                    ids.pop(0)
                    todo.append((a, b))
                    continue
                raise CTraderError("NO_TRENDBARS_REPLY",
                                   f"{e}; connection still alive (ping ok): the server ignores trendbar requests for "
                                   f"{info['name']} id {info['symbol_id']} digits {info['digits']} pipPosition "
                                   f"{info['pip_position']}, candidates {info.get('candidates')}") from None
            except CTraderError as e:
                if str(e.code) == "INCORRECT_BOUNDARIES" and b - a > 86400:
                    mid = a + (b - a) // 2  # window still too wide for the server: halve it
                    todo += [(a, mid), (mid, b)]
                    continue
                raise
            rows = [x for x in trendbars_to_rows(r.trendbar, info["digits"], volume=True) if a <= x[0] < b]
            if not rows:
                continue
            for x in rows:
                got[x[0]] = x
            first, last = min(x[0] for x in rows), max(x[0] for x in rows)
            if first - a > _GAP_S:
                todo.append((a, first))
            if b - (last + 60) > _GAP_S and last + 60 < b:
                todo.append((last + 60, b))
        return [got[t] for t in sorted(got)]

    def get_spot(self, symbol, timeout=None):
        """(bid, ask) via a brief spot subscription."""
        info = self.symbol(symbol)
        sid = info["symbol_id"]
        self.request(oa.ProtoOASubscribeSpotsReq(ctidTraderAccountId=self.account_id, symbolId=[sid]))
        bid = ask = None
        try:
            while bid is None or ask is None:
                ev = self._wait(lambda m, t, c: isinstance(m, oa.ProtoOASpotEvent) and m.symbolId == sid, timeout)
                if ev.HasField("bid"):
                    bid = ev.bid / 100000
                if ev.HasField("ask"):
                    ask = ev.ask / 100000
        finally:
            try:
                self.request(oa.ProtoOAUnsubscribeSpotsReq(ctidTraderAccountId=self.account_id, symbolId=[sid]))
            except Exception:
                pass
        return bid, ask

    # ---------------------------------------------------------------- positions / orders
    def _reconcile(self):
        return self.request(oa.ProtoOAReconcileReq(ctidTraderAccountId=self.account_id))

    def _pos_dict(self, p):
        td = p.tradeData
        return {"position_id": p.positionId, "symbol_id": td.symbolId, "symbol": self._symbol_names.get(td.symbolId),
                "side": model.ProtoOATradeSide.Name(td.tradeSide), "volume": td.volume, "price": p.price,
                "stop_loss": p.stopLoss if p.HasField("stopLoss") else None,
                "take_profit": p.takeProfit if p.HasField("takeProfit") else None,
                "label": td.label, "comment": td.comment, "open_time": td.openTimestamp}

    def _order_dict(self, o):
        td = o.tradeData
        return {"order_id": o.orderId, "symbol_id": td.symbolId, "symbol": self._symbol_names.get(td.symbolId),
                "type": model.ProtoOAOrderType.Name(o.orderType), "side": model.ProtoOATradeSide.Name(td.tradeSide),
                "volume": td.volume, "limit_price": o.limitPrice if o.HasField("limitPrice") else None,
                "stop_loss": o.stopLoss if o.HasField("stopLoss") else None,
                "take_profit": o.takeProfit if o.HasField("takeProfit") else None,
                "client_order_id": o.clientOrderId, "label": td.label, "comment": td.comment,
                "position_id": o.positionId}

    def get_positions(self):
        return [self._pos_dict(p) for p in self._reconcile().position]

    def get_orders(self):
        return [self._order_dict(o) for o in self._reconcile().order]

    def find_existing(self, client_order_id):
        """Open position or pending order already tagged with this client_order_id (or None)."""
        r = self._reconcile()
        return find_existing_in([self._pos_dict(p) for p in r.position],
                                [self._order_dict(o) for o in r.order], client_order_id)

    # ---------------------------------------------------------------- safety
    def check_can_trade(self, allow_live=False, opening=True):
        if opening:
            ks = str(self.settings.get("kill_switch", "off") or "off").strip().lower()
            if ks in ("on", "1", "true", "yes"):
                raise TradingRefused("kill_switch is on")
        if (self.env != "demo" or self.account_is_live) and not allow_live:
            raise TradingRefused(f"CTRADER_ENV={self.env}: live trading needs allow_live=True")

    # ---------------------------------------------------------------- trading
    def _order_pred(self, client_order_id, done_types):
        def make(cid):
            def pred(m, t, c):
                if isinstance(m, (oa.ProtoOAErrorRes, common.ProtoErrorRes, oa.ProtoOAOrderErrorEvent)):
                    return c == cid
                if not isinstance(m, oa.ProtoOAExecutionEvent):
                    return False
                mine = c == cid or (client_order_id and m.order.clientOrderId == client_order_id)
                return mine and model.ProtoOAExecutionType.Name(m.executionType) in done_types
            return pred
        return make

    def _check_volume(self, info, volume, max_volume):
        volume = int(volume)
        if volume < info["min_volume"]:
            raise TradingRefused(f"volume {volume} < symbol min {info['min_volume']}")
        if info["max_volume"] and volume > info["max_volume"]:
            raise TradingRefused(f"volume {volume} > symbol max {info['max_volume']}")
        if max_volume and volume > max_volume:
            raise TradingRefused(f"volume {volume} > max_volume {max_volume}")
        if info["step_volume"] and volume % info["step_volume"]:
            raise TradingRefused(f"volume {volume} not a multiple of step {info['step_volume']}")
        return volume

    def _prepare(self, symbol, side, volume, client_order_id, allow_live, max_volume):
        self.check_can_trade(allow_live)
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if not client_order_id:
            raise ValueError("client_order_id required (use sizing.client_order_id(entry_id))")
        info = self.symbol(symbol)
        volume = self._check_volume(info, volume, max_volume)
        existing = self.find_existing(client_order_id)
        return side, info, volume, existing

    def place_market_order(self, symbol, side, volume, stop_loss=None, take_profit=None, client_order_id=None,
                           label="SLK", allow_live=False, max_volume=None, ref_price=None):
        """Market order with broker-side SL/TP. Market orders only accept *relative* SL/TP, so they are
        derived from ref_price (default: current ask/bid), then amended to the exact absolute prices
        after the fill. Returns {status: FILLED|DUPLICATE, ...}."""
        side, info, volume, existing = self._prepare(symbol, side, volume, client_order_id, allow_live, max_volume)
        if existing:
            return {"status": "DUPLICATE", **existing}
        req = oa.ProtoOANewOrderReq(ctidTraderAccountId=self.account_id, symbolId=info["symbol_id"],
                                    orderType=model.MARKET, tradeSide=model.ProtoOATradeSide.Value(side),
                                    volume=volume, label=label[:100], comment=client_order_id,
                                    clientOrderId=client_order_id)
        if stop_loss is not None or take_profit is not None:
            if ref_price is None:
                bid, ask = self.get_spot(symbol)
                ref_price = ask if side == "BUY" else bid
            _check_sides(side, ref_price, stop_loss, take_profit)
            if stop_loss is not None:
                req.relativeStopLoss = sizing.relative_points(ref_price, stop_loss, info["digits"])
            if take_profit is not None:
                req.relativeTakeProfit = sizing.relative_points(ref_price, take_profit, info["digits"])
        ev = self.request(req, timeout=30, pred=self._order_pred(
            client_order_id, {"ORDER_FILLED", "ORDER_PARTIAL_FILL", "ORDER_REJECTED", "ORDER_CANCELLED", "ORDER_EXPIRED"}))
        res = self._exec_result(ev)
        if res["status"] in ("ORDER_FILLED", "ORDER_PARTIAL_FILL") and res.get("position_id"):
            res["status"] = "FILLED"
            try:
                self.amend_position_sltp(res["position_id"], stop_loss, take_profit, info["digits"])
            except Exception as e:  # relative SL/TP is already in place broker-side
                res["amend_error"] = str(e)
        return res

    def place_limit_order(self, symbol, side, volume, price, stop_loss=None, take_profit=None, client_order_id=None,
                          label="SLK", allow_live=False, max_volume=None, expiry=None):
        """Pending LIMIT order with absolute broker-side SL/TP. expiry: datetime/epoch -> GOOD_TILL_DATE."""
        side, info, volume, existing = self._prepare(symbol, side, volume, client_order_id, allow_live, max_volume)
        if existing:
            return {"status": "DUPLICATE", **existing}
        _check_sides(side, price, stop_loss, take_profit)
        d = info["digits"]
        req = oa.ProtoOANewOrderReq(ctidTraderAccountId=self.account_id, symbolId=info["symbol_id"],
                                    orderType=model.LIMIT, tradeSide=model.ProtoOATradeSide.Value(side),
                                    volume=volume, limitPrice=sizing.round_price(price, d), label=label[:100],
                                    comment=client_order_id, clientOrderId=client_order_id)
        if stop_loss is not None:
            req.stopLoss = sizing.round_price(stop_loss, d)
        if take_profit is not None:
            req.takeProfit = sizing.round_price(take_profit, d)
        if expiry is not None:
            req.timeInForce = model.GOOD_TILL_DATE
            req.expirationTimestamp = _ms(expiry)
        else:
            req.timeInForce = model.GOOD_TILL_CANCEL
        ev = self.request(req, timeout=30, pred=self._order_pred(
            client_order_id, {"ORDER_ACCEPTED", "ORDER_FILLED", "ORDER_REJECTED", "ORDER_CANCELLED"}))
        res = self._exec_result(ev)
        if res["status"] == "ORDER_ACCEPTED":
            res["status"] = "PENDING"
        return res

    def amend_position_sltp(self, position_id, stop_loss=None, take_profit=None, digits=5):
        if stop_loss is None and take_profit is None:
            return None
        req = oa.ProtoOAAmendPositionSLTPReq(ctidTraderAccountId=self.account_id, positionId=int(position_id))
        if stop_loss is not None:
            req.stopLoss = sizing.round_price(stop_loss, digits)
        if take_profit is not None:
            req.takeProfit = sizing.round_price(take_profit, digits)
        return self.request(req)

    def close_position(self, position_id, volume=None, allow_live=False):
        """Close (fully, or `volume`) at market. Allowed while the kill switch is on."""
        self.check_can_trade(allow_live, opening=False)
        if volume is None:
            pos = [p for p in self.get_positions() if p["position_id"] == int(position_id)]
            if not pos:
                raise KeyError(f"position {position_id} not open")
            volume = pos[0]["volume"]
        ev = self.request(oa.ProtoOAClosePositionReq(ctidTraderAccountId=self.account_id,
                                                     positionId=int(position_id), volume=int(volume)),
                          timeout=30, pred=self._order_pred(None, {"ORDER_FILLED", "ORDER_PARTIAL_FILL",
                                                                   "ORDER_REJECTED", "ORDER_CANCELLED"}))
        return self._exec_result(ev)

    def cancel_order(self, order_id, allow_live=False):
        self.check_can_trade(allow_live, opening=False)
        ev = self.request(oa.ProtoOACancelOrderReq(ctidTraderAccountId=self.account_id, orderId=int(order_id)),
                          pred=self._order_pred(None, {"ORDER_CANCELLED", "ORDER_CANCEL_REJECTED"}))
        return self._exec_result(ev)

    def _exec_result(self, ev):
        status = model.ProtoOAExecutionType.Name(ev.executionType)
        out = {"status": status, "order_id": ev.order.orderId if ev.HasField("order") else None,
               "position_id": ev.position.positionId if ev.HasField("position") else None}
        if ev.HasField("deal"):
            out["price"] = ev.deal.executionPrice
            out["volume"] = ev.deal.filledVolume
        if ev.HasField("errorCode"):
            out["error"] = ev.errorCode
        if status in ("ORDER_REJECTED", "ORDER_CANCEL_REJECTED"):
            raise CTraderError(ev.errorCode or status, str(out))
        return out


# ------------------------------------------------------------------ pure helpers (unit-tested)
def _check_sides(side, price, stop_loss, take_profit):
    if stop_loss is not None and ((side == "BUY") != (stop_loss < price)):
        raise ValueError(f"stop_loss {stop_loss} on wrong side of {price} for {side}")
    if take_profit is not None and ((side == "BUY") != (take_profit > price)):
        raise ValueError(f"take_profit {take_profit} on wrong side of {price} for {side}")


def trendbars_to_rows(bars, digits=5, volume=False):
    """ProtoOATrendbar list -> rows (t UTC seconds of the bar open, open, high, low, close[, volume]). Prices are
    sent as integers in 1/100000 whatever the symbol's digits."""
    rows = []
    for tb in bars:
        lo = tb.low
        row = (tb.utcTimestampInMinutes * 60,
               round((lo + tb.deltaOpen) / 100000, digits), round((lo + tb.deltaHigh) / 100000, digits),
               round(lo / 100000, digits), round((lo + tb.deltaClose) / 100000, digits))
        rows.append(row + (int(tb.volume),) if volume else row)
    return rows


def rows_to_frame(rows):
    import pandas as pd
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close"])
    df.index = pd.to_datetime(df.pop("t"), unit="s", utc=True)
    return df[~df.index.duplicated()].sort_index()


def find_existing_in(positions, orders, client_order_id):
    for p in positions:
        if client_order_id in (p.get("comment"), p.get("label")):
            return {"kind": "position", **p}
    for o in orders:
        if client_order_id in (o.get("client_order_id"), o.get("comment"), o.get("label")):
            return {"kind": "order", **o}
    return None
