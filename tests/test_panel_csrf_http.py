from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from panel.app import create_app


class FakeData:
    def __init__(self):
        self.files = {
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/panel_live_feed.json": [],
            "data/custom_sources.json": [],
            "data/newsroom_settings.json": {"auto_publish": True, "emergency_lock": False},
            "state.json": {"news_seen": []},
        }

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        return None


def _production_app():
    return create_app(
        {
            "SECRET_KEY": "csrf-http-test-secret",
            "PANEL_PASSWORD_HASH": generate_password_hash("panel-pass"),
            "DATA_BACKEND": FakeData(),
            "LIVE_FEED_TRANSLATOR": lambda text: text,
        }
    )


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    return match.group(1)


def test_plain_http_login_keeps_session_cookie_and_accepts_csrf(monkeypatch):
    monkeypatch.delenv("PANEL_COOKIE_SECURE", raising=False)
    app = _production_app()
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


def test_https_cookie_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("PANEL_COOKIE_SECURE", "1")
    app = _production_app()
    assert app.config["SESSION_COOKIE_SECURE"] is True
