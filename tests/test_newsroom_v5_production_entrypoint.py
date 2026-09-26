from __future__ import annotations

import importlib
import sys

from werkzeug.security import generate_password_hash

import panel.app as panel_app


class FakeData:
    def read_json(self, path, default):
        return default, "sha"

    def write_json(self, *args, **kwargs):
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        return None


def _load(monkeypatch, **env):
    monkeypatch.setenv("PANEL_SECRET_KEY", "v5-entrypoint-secret")
    monkeypatch.setenv("PANEL_PASSWORD_HASH", generate_password_hash("pass"))
    monkeypatch.setenv("GITHUB_DATA_TOKEN", "test-token")
    monkeypatch.delenv("PANEL_LOCAL_ROOT", raising=False)
    for name in ("NEWSROOM_STORE_BACKEND", "NEWSROOM_V5_UI_ENABLED", "NEWSROOM_SQLITE_PATH"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(panel_app, "GitHubJsonRepository", lambda *args, **kwargs: FakeData())
    sys.modules.pop("panel.wsgi", None)
    return importlib.import_module("panel.wsgi").app


def _admin(client):
    with client.session_transaction() as session:
        session["admin"] = True


def test_production_entrypoint_mounts_v5_but_keeps_it_inert_by_default(monkeypatch):
    app = _load(monkeypatch)
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/v5/review" in rules and "/api/v5/events" in rules and "/v5" in rules
    assert app.extensions["newsroom_v5_store"] is None
    client = app.test_client(); _admin(client)
    assert client.get("/v5").status_code == 404
    assert client.get("/api/v5/review").status_code == 503
    assert app.test_client().get("/login").status_code == 200


def test_production_entrypoint_serves_v5_when_explicitly_enabled(monkeypatch, tmp_path):
    app = _load(
        monkeypatch,
        NEWSROOM_STORE_BACKEND="sqlite",
        NEWSROOM_SQLITE_PATH=str(tmp_path / "v5.db"),
        NEWSROOM_V5_UI_ENABLED="true",
    )
    client = app.test_client(); _admin(client)
    assert client.get("/v5").status_code == 200
    assert client.get("/api/v5/review").get_json() == {"items": [], "next_cursor": None}
