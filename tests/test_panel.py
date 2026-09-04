from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from panel.app import create_app


class FakeData:
    def __init__(self):
        self.files = {
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/custom_sources.json": [],
            "state.json": {"news_seen": []},
        }

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        seen = [x for x in self.files["state.json"].get("news_seen", []) if x != key]
        seen.insert(0, key)
        self.files["state.json"]["news_seen"] = seen


def _app():
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "PANEL_PASSWORD_HASH": generate_password_hash("panel-pass"),
            "TELEGRAM_BOT_TOKEN": "telegram-secret-value",
            "GITHUB_DATA_TOKEN": "github-secret-value",
            "DATA_BACKEND": FakeData(),
        }
    )


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    return match.group(1)


def _login(client):
    page = client.get("/login")
    token = _csrf(page.get_data(as_text=True))
    return client.post("/login", data={"password": "panel-pass", "csrf_token": token}, follow_redirects=True)


def test_private_route_redirects_to_login():
    app = _app()
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_invalid_password_is_rejected():
    app = _app()
    client = app.test_client()
    page = client.get("/login")
    token = _csrf(page.get_data(as_text=True))
    response = client.post("/login", data={"password": "wrong", "csrf_token": token}, follow_redirects=True)
    assert "رمز ورود درست نیست" in response.get_data(as_text=True)


def test_authenticated_dashboard_loads():
    app = _app()
    client = app.test_client()
    response = _login(client)
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "داشبورد" in text
    assert "نیاز به بررسی" in text


def test_mutation_without_csrf_is_rejected():
    app = _app()
    client = app.test_client()
    _login(client)
    response = client.post("/sources/x", data={"x-handle": "@BarakRavid"})
    assert response.status_code == 400


def test_secret_values_never_render_in_html():
    app = _app()
    client = app.test_client()
    response = _login(client)
    text = response.get_data(as_text=True)
    assert "telegram-secret-value" not in text
    assert "github-secret-value" not in text
    assert "test-secret-key" not in text
