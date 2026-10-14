"""Smoke test: connect, auth, print balance + last 5 EURUSD H1 bars. Places nothing unless --test-order (demo only).

    python -m ctrader.smoke [--symbol EURUSD] [--test-order]
Exits 0 with a message when the secrets are not configured (so CI stays green before setup).
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from ctrader import sizing, tokens
from ctrader.client import CTraderClient, CTraderError, _norm
from ctrader.framing import oa

REQUIRED = ("CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--test-order", action="store_true", help="demo only: open min-volume market order, then close it")
    args = ap.parse_args(argv)

    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if not os.environ.get("CTRADER_ACCESS_TOKEN") and not os.environ.get("DATABASE_URL"):
        missing.append("CTRADER_ACCESS_TOKEN")
    if missing:
        print(f"cTrader smoke skipped: secrets not set: {', '.join(missing)}. See ctrader/README.md.")
        return 0

    env = (os.environ.get("CTRADER_ENV") or "demo").lower()
    print(f"cTrader env: {env}")
    settings = tokens.default_settings(strict=args.test_order)
    try:
        return run(args, env, settings)
    except CTraderError as e:
        print(f"cTrader refused: {e.code} {e.description}")
        if "AUTH" in str(e.code).upper() or "TOKEN" in str(e.code).upper():
            print("hint: while app 43716 is still 'Submitted' (not 'Active') Spotware may refuse auth; "
                  "otherwise re-issue tokens (ctrader/README.md).")
        return 1


def run(args, env, settings):
    with CTraderClient(env=env, settings=settings) as c:
        t = c.get_trader()
        print(f"account {t['login']} ({t['broker']}, ctid {c.account_id}, live={c.account_is_live}): "
              f"balance {t['balance']:.2f}, leverage 1:{t['leverage']:.0f}")
        info = c.symbol(args.symbol)
        print(f"{info['name']}: id {info['symbol_id']}, digits {info['digits']}, pipPosition {info['pip_position']}, "
              f"lotSize {info['lot_size']}, minVolume {info['min_volume']}, step {info['step_volume']}, "
              f"candidates {info.get('candidates')}")
        print(similar_symbols(c, args.symbol))
        print(pip_check(args.symbol, info))
        now = datetime.now(timezone.utc)
        try:
            df = c.get_trendbars(args.symbol, "H1", now - timedelta(days=7), now)
        except Exception as e:
            print(f"H1 trendbars FAILED: {type(e).__name__}: {e}")
            for line in probe(c, args.symbol, now):
                print(line)
            return 1
        print(f"last 5 H1 bars ({len(df)} in 7 days):")
        print(df.tail(5).to_string())

        pv = sizing.pip_value_per_lot(info["pip_position"], info["lot_size"])
        vol = sizing.volume_for_risk(t["balance"], 0.5, 20, pv, info["lot_size"], info["min_volume"],
                                     info["step_volume"], info["max_volume"])
        print(f"sizing example (0.5% risk, 20 pip stop, quote ccy = account ccy): volume {vol} "
              f"= {sizing.volume_to_lots(vol, info['lot_size']):.2f} lots")
        pos = c.get_positions()
        print(f"open positions: {len(pos)}, pending orders: {len(c.get_orders())}")

        if args.test_order:
            if env != "demo" or c.account_is_live:
                print("--test-order refused: only allowed on demo")
                return 1
            bid, ask = c.get_spot(args.symbol)
            pip = sizing.pip_size(info["pip_position"])
            cid = sizing.client_order_id(f"smoke{int(time.time())}")
            print(f"spot bid {bid} ask {ask}; test BUY {info['min_volume']} with SL/TP 20 pips, id {cid}")
            r = c.place_market_order(args.symbol, "BUY", info["min_volume"], stop_loss=ask - 20 * pip,
                                     take_profit=ask + 20 * pip, client_order_id=cid, label="SLK-smoke", ref_price=ask)
            print(f"order: {r}")
            again = c.place_market_order(args.symbol, "BUY", info["min_volume"], stop_loss=ask - 20 * pip,
                                         take_profit=ask + 20 * pip, client_order_id=cid, label="SLK-smoke", ref_price=ask)
            print(f"idempotency re-send -> {again['status']}")
            if r.get("position_id"):
                print(f"close: {c.close_position(r['position_id'])}")
    return 0


def similar_symbols(c, symbol):
    """Every enabled broker symbol whose name contains the requested one (e.g. XAUUSD, XAUUSD.r, XAU/USD)."""
    want = _norm(symbol)
    light = c.request(oa.ProtoOASymbolsListReq(ctidTraderAccountId=c.account_id, includeArchivedSymbols=False)).symbol
    hits = [(s.symbolId, s.symbolName, s.enabled) for s in light if want in _norm(s.symbolName)]
    return f"symbols like {want}: " + (", ".join(f"{n} id {i}{'' if e else ' (disabled)'}" for i, n, e in hits)
                                       or "none")


def pip_check(symbol, info):
    try:
        from slk import instruments
    except Exception:  # slk needs pandas/numpy only; the smoke job installs them
        return "pip table not available"
    m = instruments.mismatch(symbol, info["pip_position"])
    return m or f"pip {10.0 ** -info['pip_position']:g} = table {instruments.static(symbol)[0]:g}"


def probe(c, symbol, now):
    """After a failed H1 request: is the link alive, and does any other period / a short window answer?"""
    out = [f"ping after the failure: {'ok' if c.ping() else 'NO ANSWER (connection dead)'}"]
    for period, span in (("H1", timedelta(hours=6)), ("D1", timedelta(days=30)), ("M1", timedelta(hours=2))):
        try:
            rows = c.trendbar_rows(symbol, period, now - span, now)
            out.append(f"{period} {span}: {len(rows)} bars" + (f", last {rows[-1][:5]}" if rows else ""))
        except Exception as e:
            out.append(f"{period} {span}: {type(e).__name__}: {e}")
    return out


if __name__ == "__main__":
    sys.exit(main())
