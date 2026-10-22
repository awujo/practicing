"""Request/job scoped data isolation. Owner retains legacy tables and settings."""
from contextvars import ContextVar
from contextlib import contextmanager
import os
import re

USER = ContextVar("slk_user", default=None)
TABLES = {"bias", "entries", "orders", "tf_state", "settings", "runs"}
STARTER = {"pairs": "EURUSD,GBPUSD,USDJPY", "stories": "D,W", "auto_trade": "off"}


def owner_id():
    return int(os.environ.get("TELEGRAM_CHAT_ID") or "1410229777")


@contextmanager
def scope(uid):
    token = USER.set(int(uid) if uid is not None else None)
    try:
        yield
    finally:
        USER.reset(token)


def tenant_id():
    uid = USER.get()
    return uid if uid is not None and uid != owner_id() else None


def scoped_sql(sql):
    """Scope this project's single-table SQL. Unsupported tenant queries fail closed.

    IDs are validated integers, never interpolated request text. Parenthesize existing
    predicates so OR clauses cannot escape the scope. No joins/subqueries allowed.
    """
    uid = tenant_id()
    if uid is None:
        return sql
    matches = list(re.finditer(r"\b(FROM|UPDATE|INTO)\s+([a-z_]+)\b", sql, re.I))
    if sql.lstrip().upper().startswith("INSERT"):
        matches = matches[:1]
    scoped = [m for m in matches if m[2].lower() in TABLES]
    if not scoped:
        return sql
    if len(matches) != 1 or len(scoped) != 1 or re.search(r"\b(JOIN|UNION|DELETE)\b|;", sql, re.I):
        raise ValueError("unsupported scoped SQL")
    m = scoped[0]
    sql = sql[:m.start(2)] + "tenant_" + sql[m.start(2):]
    if m[1].upper() == "INTO":
        sql, n = re.subn(r"(\btenant_\w+\s*\()", r"\1user_id, ", sql, count=1)
        sql, v = re.subn(r"\bVALUES\s*\(", f"VALUES ({int(uid)}, ", sql, count=1, flags=re.I)
        if n != 1 or v != 1:
            raise ValueError("unsupported scoped INSERT")
        return sql
    tail = re.search(r"\b(ORDER\s+BY|GROUP\s+BY|LIMIT)\b", sql, re.I)
    base, suffix = (sql[:tail.start()], sql[tail.start():]) if tail else (sql, "")
    where = re.search(r"\bWHERE\b", base, re.I)
    if where:
        base = base[:where.start()] + f"WHERE user_id={int(uid)} AND (" + base[where.end():].strip() + ") "
    else:
        base = base.rstrip() + f" WHERE user_id={int(uid)} "
    return base + suffix


def schema_sql(source):
    """Build new isolated tables from current canonical definitions; no legacy rows changed."""
    source = re.sub(r"--[^\n]*", "", source)
    out = ["CREATE TABLE IF NOT EXISTS app_users (user_id BIGINT PRIMARY KEY, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"]
    for statement in source.split(";"):
        m = re.search(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\(", statement)
        if not m or m[1] not in TABLES:
            continue
        table = m[1]
        ddl = statement[m.start():].replace(f"EXISTS {table}", f"EXISTS tenant_{table}", 1)
        start = ddl.index("(") + 1
        ddl = ddl[:start] + "\n user_id BIGINT NOT NULL,\n" + ddl[start:]
        ddl = re.sub(r"UNIQUE KEY (\w+) \(", r"UNIQUE KEY \1 (user_id, ", ddl)
        if table == "bias":
            ddl = ddl.replace(") ENGINE=", ", UNIQUE KEY uq_tenant_bias_id (user_id, id)) ENGINE=")
        if table == "entries":
            ddl = ddl.replace("CONSTRAINT fk_entries_bias FOREIGN KEY (bias_id) REFERENCES bias(id)",
                              "CONSTRAINT fk_tenant_entries_bias FOREIGN KEY (user_id, bias_id) REFERENCES tenant_bias(user_id, id)")
        if table == "tf_state":
            ddl = ddl.replace("PRIMARY KEY (pair, story)", "PRIMARY KEY (user_id, pair, story)")
        elif table == "settings":
            ddl = ddl.replace("k  VARCHAR(64) PRIMARY KEY", "k  VARCHAR(64)")
            ddl = ddl.replace(") ENGINE=", ", PRIMARY KEY (user_id, k)) ENGINE=")
        out.append(ddl)
    return out
