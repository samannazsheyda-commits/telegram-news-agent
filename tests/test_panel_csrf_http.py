from __future__ import annotations

import importlib
import re
import sys

from werkzeug.security import generate_password_hash

import panel.app as panel_app


class FakeData:
    def __init__(self):
        self.files = {"data/weather_preview.json": {}}

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        return None


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    return match.group(1)


def _load_production_wsgi(monkeypatch, *, secure: str | None = None):
    monkeypatch.setenv("PANEL_SECRET_KEY", "csrf-http-test-secret")
    monkeypatch.setenv("PANEL_PASSWORD_HASH", generate_password_hash("panel-pass"))
    monkeypatch.setenv("GITHUB_DATA_TOKEN", "test-token")
    monkeypatch.delenv("PANEL_LOCAL_ROOT", raising=False)
    monkeypatch.setattr(panel_app, "GitHubJsonRepository", lambda *args, **kwargs: FakeData())
    if secure is None:
        monkeypatch.delenv("PANEL_COOKIE_SECURE", raising=False)
    else:
        monkeypatch.setenv("PANEL_COOKIE_SECURE", secure)
    sys.modules.pop("panel.wsgi", None)
    return importlib.import_module("panel.wsgi").app


def test_plain_http_wsgi_login_keeps_session_cookie_and_accepts_csrf(monkeypatch):
    app = _load_production_wsgi(monkeypatch)
    assert app.config["SESSION_COOKIE_SECURE"] is False

    client = app.test_client()
    page = client.get("/login", base_url="http://panel.local")
    cookie = page.headers.get("Set-Cookie", "")
    assert "Secure" not in cookie

    response = client.post(
        "/login",
        base_url="http://panel.local",
        data={"password": "panel-pass", "csrf_token": _csrf(page.get_data(as_text=True))},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_https_wsgi_cookie_can_be_enabled_explicitly(monkeypatch):
    app = _load_production_wsgi(monkeypatch, secure="1")
    assert app.config["SESSION_COOKIE_SECURE"] is True
