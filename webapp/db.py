"""DB access for the Mini App. Uses slk.db.connect() when it exists, else a local PyMySQL connect()."""
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pymysql
import pymysql.cursors

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

try:  # shared helper (CONTRACT.md); optional
    from slk.db import connect as _slk_connect  # type: ignore
except Exception:  # noqa: BLE001
    _slk_connect = None


def _local_connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    u = urlparse(url.strip().strip('"').strip("'").strip())
    q = parse_qs(u.query)
    ssl_mode = (q.get("ssl-mode") or q.get("ssl_mode") or ["REQUIRED"])[0].upper()
    ssl = None if ssl_mode == "DISABLED" else {"ssl": {}}
    kw = dict(
        host=u.hostname,
        port=u.port or 3306,
        user=unquote(u.username or ""),
        password=os.environ.get("DATABASE_PASSWORD", "").strip() or unquote(u.password or "").strip(),
        database=(u.path or "/").lstrip("/") or None,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10,
        init_command="SET time_zone = '+00:00'",  # TIMESTAMP columns read as UTC (the app shows local days)
    )
    if ssl:
        kw["ssl"] = ssl["ssl"] or {"check_hostname": False}
    return pymysql.connect(**kw)


def connect():
    if _slk_connect is not None:
        conn = _slk_connect()
        try:
            conn.cursorclass = pymysql.cursors.DictCursor
            conn.autocommit(True)
        except Exception:  # noqa: BLE001
            pass
        return conn
    return _local_connect()


from slk import tenancy

def query(sql, args=None):
    sql = tenancy.scoped_sql(sql)
    conn = connect()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())
    finally:
        conn.close()


def execute(sql, args=None):
    sql = tenancy.scoped_sql(sql)
    conn = connect()
    try:
        with conn.cursor() as cur:
            n = cur.execute(sql, args)
        conn.commit()
        return n
    finally:
        conn.close()


def schema_path():
    p = ROOT / "db" / "schema.sql"
    return p if p.exists() else HERE / "schema.sql"


def split_sql(text):
    text = re.sub(r"--[^\n]*", "", text)
    return [s.strip() for s in text.split(";") if s.strip()]


def ensure_schema():
    conn = connect()
    try:
        with conn.cursor() as cur:
            source = schema_path().read_text()
            for stmt in split_sql(source) + tenancy.schema_sql(source):
                cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def get_settings():
    return {**(tenancy.STARTER if tenancy.tenant_id() else {}),
            **{r["k"]: r["v"] for r in query("SELECT k, v FROM settings")}}


def set_setting(k, v):
    execute("INSERT INTO settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", (k, v))


def set_settings(changes):
    """Persist one validated form atomically using one connection, including tenant scope."""
    if not changes:
        return
    sql = tenancy.scoped_sql("INSERT INTO settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)")
    conn = connect()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.executemany(sql, list(changes.items()))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
