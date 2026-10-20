"""OAuth tokens + settings storage for the cTrader client.

Tokens are read from the DB `settings` table (keys ctrader_access_token, ctrader_refresh_token,
ctrader_token_expiry = unix seconds) when available, else from env CTRADER_ACCESS_TOKEN /
CTRADER_REFRESH_TOKEN. Refreshed tokens are written back to the DB (the refresh call invalidates
the previous refresh token, so without a DB the new pair is only kept in memory for this process).

CLI (one-time setup, see ctrader/README.md):
    python -m ctrader.tokens auth-url --redirect-uri https://example.com/callback
    python -m ctrader.tokens exchange --code CODE --redirect-uri https://example.com/callback
"""
import argparse
import json
import os
import sys
import time
import urllib.parse

AUTH_URI = "https://openapi.ctrader.com/apps/auth"
TOKEN_URI = "https://openapi.ctrader.com/apps/token"
REFRESH_MARGIN_S = 3 * 24 * 3600  # refresh when < 3 days left


class MemorySettings:
    """Fallback settings store (no DB): env-seeded, process-local."""

    def __init__(self, initial=None):
        self.d = dict(initial or {})

    def get(self, k, default=None):
        return self.d.get(k, default)

    def set(self, k, v):
        self.d[k] = None if v is None else str(v)


class DbSettings:
    """Adapter over bishop/db.py (get_setting / set_setting) as defined in CONTRACT.md.

    OUR CHOICE (Bishop bot shares the owner's single cTrader demo login with the Kevin bot): a cTrader refresh
    invalidates the previous refresh token, so if this bot refreshed too it would break the Kevin bot's stored
    tokens. By default the ctrader_* keys are therefore BORROWED read-only from the Kevin table `settings`
    (env CTRADER_TOKEN_TABLE, default `settings`; set it empty to use bishop_settings and refresh here instead).
    A borrowed token is never refreshed or written by this bot: the Kevin hourly job keeps it fresh; when it is
    expired the candle layer falls back to Dukascopy.
    """

    def __init__(self, db, token_table=None):
        self.db = db
        self.token_table = os.environ.get("CTRADER_TOKEN_TABLE", "settings") if token_table is None else token_table
        self.borrowed = bool(self.token_table)

    def get(self, k, default=None):
        if self.borrowed and k.startswith("ctrader_"):
            try:
                rows = self.db.query(f"SELECT v FROM `{self.token_table}` WHERE k=%s", (k,))
            except Exception:
                return default
            return rows[0]["v"] if rows and rows[0]["v"] is not None else default
        return self.db.get_setting(k, default)

    def set(self, k, v):
        if self.borrowed and k.startswith("ctrader_"):
            return  # never write the other bot's tokens
        self.db.set_setting(k, None if v is None else str(v))


def default_settings(strict=True):
    """DbSettings when DATABASE_URL is set, else MemorySettings. With strict=True an unusable DB
    raises (so the kill switch is never silently skipped); strict=False falls back to memory."""
    if os.environ.get("DATABASE_URL"):
        try:
            from bishop import db  # optional dependency, see CONTRACT.md
            db.get_setting("kill_switch", "off")
            return DbSettings(db)
        except Exception as e:
            if strict:
                raise
            print(f"warning: DB settings unavailable ({type(e).__name__}); using env tokens only")
    return MemorySettings()


def load_tokens(settings):
    return {
        "access_token": settings.get("ctrader_access_token") or os.environ.get("CTRADER_ACCESS_TOKEN"),
        "refresh_token": settings.get("ctrader_refresh_token") or os.environ.get("CTRADER_REFRESH_TOKEN"),
        "expiry": _to_float(settings.get("ctrader_token_expiry")),
    }


def needs_refresh(tokens, now=None):
    exp = tokens.get("expiry")
    if not exp:
        return False  # unknown expiry: refresh only on an auth failure
    return exp - (now or time.time()) < REFRESH_MARGIN_S


def _to_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _token_request(params, http_get=None):
    if http_get is None:
        import requests
        http_get = lambda url, params: requests.get(url, params=params, timeout=30,  # noqa: E731
                                                    headers={"Accept": "application/json"}).json()
    data = http_get(TOKEN_URI, params)
    if not data.get("accessToken") or data.get("errorCode"):
        raise RuntimeError(f"token request failed: {data.get('errorCode')} {data.get('description')}")
    return data


def refresh_tokens(settings=None, refresh_token=None, client_id=None, client_secret=None, http_get=None):
    """OAuth refresh. Stores new access/refresh token + expiry in settings; returns the tokens dict."""
    settings = settings if settings is not None else default_settings()
    if getattr(settings, "borrowed", False):
        raise RuntimeError("cTrader tokens are borrowed from the Kevin bot (read-only); refresh is done there")
    refresh_token = refresh_token or load_tokens(settings)["refresh_token"]
    if not refresh_token:
        raise RuntimeError("no refresh token (CTRADER_REFRESH_TOKEN / settings.ctrader_refresh_token)")
    data = _token_request({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id or os.environ["CTRADER_CLIENT_ID"],
        "client_secret": client_secret or os.environ["CTRADER_CLIENT_SECRET"],
    }, http_get)
    return _store(settings, data)


def _store(settings, data):
    expiry = int(time.time() + int(data.get("expiresIn") or 0)) if data.get("expiresIn") else None
    settings.set("ctrader_access_token", data["accessToken"])
    if data.get("refreshToken"):
        settings.set("ctrader_refresh_token", data["refreshToken"])
    if expiry:
        settings.set("ctrader_token_expiry", expiry)
    return {"access_token": data["accessToken"], "refresh_token": data.get("refreshToken"), "expiry": expiry}


def auth_url(client_id, redirect_uri, scope="trading"):
    q = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "scope": scope})
    return f"{AUTH_URI}?{q}"


def exchange_code(code, redirect_uri, client_id, client_secret, http_get=None):
    return _token_request({
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id, "client_secret": client_secret,
    }, http_get)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m ctrader.tokens")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auth-url")
    a.add_argument("--redirect-uri", required=True)
    e = sub.add_parser("exchange")
    e.add_argument("--code", required=True)
    e.add_argument("--redirect-uri", required=True)
    e.add_argument("--save-db", action="store_true", help="also write tokens to DB settings")
    sub.add_parser("refresh", help="refresh now and store in DB settings")
    args = ap.parse_args(argv)
    cid = os.environ.get("CTRADER_CLIENT_ID")
    if not cid:
        sys.exit("set CTRADER_CLIENT_ID (and CTRADER_CLIENT_SECRET) in the environment")
    if args.cmd == "auth-url":
        print(auth_url(cid, args.redirect_uri))
    elif args.cmd == "exchange":
        data = exchange_code(args.code, args.redirect_uri, cid, os.environ["CTRADER_CLIENT_SECRET"])
        if args.save_db:
            _store(default_settings(), data)
        # Printed on purpose: this is the one-time, local, interactive setup step.
        print(json.dumps({k: data.get(k) for k in ("accessToken", "refreshToken", "expiresIn", "tokenType")}, indent=1))
    else:
        t = refresh_tokens()
        print(f"refreshed; expires at {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(t['expiry'] or 0))}")


if __name__ == "__main__":
    main()
