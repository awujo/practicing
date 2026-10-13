"""Re-check 2: DATABASE_PASSWORD fallback + workflow env consistency."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webapp"))

import db as webdb  # noqa: E402


def test_webapp_local_connect_password_fallback(monkeypatch):
    seen = {}
    monkeypatch.setattr(webdb.pymysql, "connect", lambda **kw: seen.update(kw) or "conn")
    monkeypatch.setenv("DATABASE_URL", "mysql://avnadmin@h.example:1234/defaultdb?ssl-mode=REQUIRED")
    monkeypatch.setenv("DATABASE_PASSWORD", "  s3cret\n")
    assert webdb._local_connect() == "conn"
    assert seen["password"] == "s3cret" and seen["port"] == 1234 and seen["user"] == "avnadmin"


def test_slk_parse_url_password_fallback(monkeypatch):
    from slk import db
    monkeypatch.setenv("DATABASE_PASSWORD", " pw ")
    assert db.parse_url("mysql://u@h/d")["password"] == "pw"
    assert db.parse_url("mysql://u:inurl@h/d")["password"] == "inurl"


def test_workflows_valid_and_pass_password_with_url():
    for f in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = f.read_text()
        yaml.safe_load(text)
        if "secrets.DATABASE_URL" in text:
            assert "secrets.DATABASE_PASSWORD" in text, f.name
