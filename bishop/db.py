"""MySQL access (Bishop bot: ONLY tables with the bishop_ prefix; the Kevin tables are never written). DATABASE_URL = mysql://user:pass@host:port/db?ssl-mode=REQUIRED (Aiven).

SSL is always on unless the URL says ssl-mode=DISABLED. Aiven uses its own CA: set DATABASE_CA (path to the
CA file, or the PEM text itself) to verify it; without it the link is still encrypted but the cert is not checked.
"""
import os
import re
import ssl
import tempfile
from urllib.parse import parse_qs, unquote, urlparse

SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "schema.sql")
# columns added after the first release: CREATE TABLE IF NOT EXISTS does not add them to an existing table
MIGRATIONS = ()


def parse_url(url):
    """DATABASE_URL -> dict of connect kwargs (without ssl) plus 'ssl_mode'."""
    u = urlparse(url.strip().strip('"').strip("'").strip())
    if u.scheme not in ("mysql", "mysql+pymysql"):
        raise ValueError("DATABASE_URL must start with mysql://")
    q = {k.lower().replace("_", "-"): v[0] for k, v in parse_qs(u.query).items()}
    return {
        "host": u.hostname, "port": u.port or 3306,
        "user": unquote(u.username or ""),
        # a non-empty secret DATABASE_PASSWORD wins over the URL password (URL may hold a stale one)
        "password": os.environ.get("DATABASE_PASSWORD", "").strip() or unquote(u.password or "").strip(),
        "database": unquote((u.path or "/").lstrip("/")) or None,
        "ssl_mode": q.get("ssl-mode", "REQUIRED").upper(),
    }


def _ssl_context(mode):
    if mode == "DISABLED":
        return None
    ca = os.environ.get("DATABASE_CA", "").strip()
    if ca:
        if "BEGIN CERTIFICATE" in ca:
            f = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
            f.write(ca)
            f.close()
            ca = f.name
        ctx = ssl.create_default_context(cafile=ca)
        ctx.check_hostname = mode == "VERIFY_IDENTITY"
        return ctx
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # encrypted, not verified (no CA given)
    return ctx


def connect(url=None):
    """PyMySQL connection, DictCursor, autocommit on."""
    import pymysql
    import pymysql.cursors
    p = parse_url(url or os.environ["DATABASE_URL"])
    mode = p.pop("ssl_mode")
    return pymysql.connect(**p, ssl=_ssl_context(mode), charset="utf8mb4", autocommit=True,
                           cursorclass=pymysql.cursors.DictCursor, connect_timeout=15, read_timeout=60,
                           write_timeout=60, init_command="SET time_zone = '+00:00'")  # TIMESTAMPs read as UTC


_conn = None


def _c():
    global _conn
    if _conn is None or not _conn.open:
        _conn = connect()
    else:
        _conn.ping(reconnect=True)
    return _conn


def query(sql, args=None):
    with _c().cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def execute(sql, args=None):
    with _c().cursor() as cur:
        cur.execute(sql, args)
        return cur.lastrowid


def apply_schema(path=SCHEMA):
    """Run every statement of db/schema.sql (idempotent)."""
    text = re.sub(r"--[^\n]*", "", open(path).read())
    for stmt in (s.strip() for s in text.split(";")):
        if stmt:
            execute(stmt)
    migrate()


def migrate():
    """Add MIGRATIONS columns that are missing (MySQL 8 has no ADD COLUMN IF NOT EXISTS)."""
    for table, col, ddl in MIGRATIONS:
        n = query("SELECT COUNT(*) AS n FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
                  "AND TABLE_NAME = %s AND COLUMN_NAME = %s", (table, col))
        if not n[0]["n"]:
            execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def get_setting(k, default=None):
    rows = query("SELECT v FROM bishop_settings WHERE k=%s", (k,))
    return rows[0]["v"] if rows and rows[0]["v"] is not None else default


def get_settings():
    """All rows of table `bishop_settings` as {k: v}."""
    return {r["k"]: r["v"] for r in query("SELECT k, v FROM bishop_settings")}


def set_setting(k, v):
    execute("INSERT INTO bishop_settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v=VALUES(v)", (k, str(v)))


def start_run(job, planned_at, started_at):
    return execute("INSERT INTO bishop_runs (job, planned_at, started_at) VALUES (%s, %s, %s)",
                   (job, planned_at, started_at))


def finish_run(run_id, ok, note=""):
    execute("UPDATE bishop_runs SET finished_at=UTC_TIMESTAMP(), ok=%s, note=%s WHERE id=%s",
            (int(bool(ok)), note[:60000], run_id))


def last_run(job, ok=True):
    rows = query("SELECT * FROM bishop_runs WHERE job=%s AND ok=%s ORDER BY started_at DESC LIMIT 1",
                 (job, int(ok)))
    return rows[0] if rows else None
