"""Shared cTrader tokens stay read-only through database and fallback paths."""
import re
from pathlib import Path

import pytest

from bishop import db
from ctrader import tokens


@pytest.fixture(autouse=True)
def shared_policy(monkeypatch):
    monkeypatch.delenv("CTRADER_TOKEN_TABLE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def forbidden_http(*args, **kwargs):
    pytest.fail("a shared-token refresh must never contact the OAuth endpoint")


def test_no_database_fallback_cannot_rotate_shared_env_token(monkeypatch):
    monkeypatch.setenv("CTRADER_REFRESH_TOKEN", "shared-refresh-placeholder")
    store = tokens.default_settings()
    assert store.borrowed
    with pytest.raises(RuntimeError, match="read-only"):
        tokens.refresh_tokens(store, http_get=forbidden_http)


def test_database_failure_fallback_keeps_shared_policy(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://unused")

    def unavailable(*args):
        raise ConnectionError("database unavailable")

    monkeypatch.setattr(db, "get_setting", unavailable)
    store = tokens.default_settings(strict=False)
    assert isinstance(store, tokens.MemorySettings) and store.borrowed
    with pytest.raises(RuntimeError, match="read-only"):
        tokens.refresh_tokens(store, http_get=forbidden_http)
    with pytest.raises(ConnectionError):
        tokens.default_settings(strict=True)


def test_memory_store_cannot_write_shared_tokens():
    store = tokens.MemorySettings({"ctrader_access_token": "existing"})
    store.set("ctrader_access_token", "replacement")
    store.set("alert_mode", "off")
    assert store.get("ctrader_access_token") == "existing"
    assert store.get("alert_mode") == "off"
    with pytest.raises(RuntimeError, match="read-only"):
        tokens._store(store, {"accessToken": "replacement", "refreshToken": "replacement-refresh"})


@pytest.mark.parametrize("name", ["settings`", "some table", "schema.settings", "a" * 65, "9settings"])
def test_token_table_rejects_unsafe_sql_identifiers(name):
    with pytest.raises(ValueError, match="plain SQL identifier"):
        tokens.DbSettings(db, token_table=name)


@pytest.mark.parametrize("name", ["settings", "_tokens2", "a" * 64, ""])
def test_token_table_allows_identifiers_and_explicit_owned_mode(name):
    store = tokens.DbSettings(db, token_table=name)
    assert store.borrowed == bool(name)


@pytest.mark.parametrize("token_table,borrowed", [("settings", True), ("", False)])
def test_database_and_fallback_preserve_same_ownership(monkeypatch, token_table, borrowed):
    monkeypatch.setenv("DATABASE_URL", "mysql://unused")
    monkeypatch.setenv("CTRADER_TOKEN_TABLE", token_table)
    monkeypatch.setattr(db, "get_setting", lambda *args: "off")
    connected = tokens.default_settings()
    assert isinstance(connected, tokens.DbSettings) and connected.borrowed is borrowed

    def unavailable(*args):
        raise ConnectionError("database unavailable")

    monkeypatch.setattr(db, "get_setting", unavailable)
    fallback = tokens.default_settings(strict=False)
    assert isinstance(fallback, tokens.MemorySettings) and fallback.borrowed is borrowed


def test_explicit_independent_token_policy_can_refresh(monkeypatch):
    monkeypatch.setenv("CTRADER_TOKEN_TABLE", "")
    store = tokens.default_settings()
    assert not store.borrowed
    calls = []

    def oauth(url, params):
        calls.append((url, params))
        return {"accessToken": "independent-new-access", "refreshToken": "independent-new-refresh", "expiresIn": 3600}

    result = tokens.refresh_tokens(store, refresh_token="independent-old-refresh", client_id="test-client",
                                   client_secret="test-secret", http_get=oauth)
    assert len(calls) == 1
    assert calls[0][1]["refresh_token"] == "independent-old-refresh"
    assert result["access_token"] == store.get("ctrader_access_token") == "independent-new-access"
    assert store.get("ctrader_refresh_token") == "independent-new-refresh"


def test_bishop_schema_executes_only_isolated_table_creates(monkeypatch):
    statements = []
    monkeypatch.setattr(db, "execute", lambda sql: statements.append(sql))
    db.apply_schema()
    tables = [re.search(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", sql).group(1) for sql in statements]
    assert set(tables) == {"bishop_settings", "bishop_runs"}
    assert Path(db.SCHEMA).is_file()
