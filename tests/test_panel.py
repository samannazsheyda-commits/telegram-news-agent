from __future__ import annotations

import re
from pathlib import Path

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
        seen = [x for x in self.files["state.json"].get("news_seen", []) if x != key]
        seen.insert(0, key)
        self.files["state.json"]["news_seen"] = seen


def _app(data=None):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "PANEL_PASSWORD_HASH": generate_password_hash("panel-pass"),
            "TELEGRAM_BOT_TOKEN": "telegram-secret-value",
            "GITHUB_DATA_TOKEN": "github-secret-value",
            "DATA_BACKEND": data or FakeData(),
            "LIVE_FEED_TRANSLATOR": lambda text: {
                "Live story 0": "خبر زنده صفر",
                "Live story 1": "خبر زنده یک",
                "Live story 2": "خبر زنده دو",
                "Live story 3": "خبر زنده سه",
                "Live story 4": "خبر زنده چهار",
            }.get(text, text),
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
    assert "اتاق فرمان جنگ" in text
    assert "توقف کامل انتشار" in text
    assert "اسکن فوری" in text
    assert "هواشناسی فردا" in text
    assert "ترافیک هوایی ایران و منطقه" in text
    assert "نفتکش‌ها و تنگه هرمز" in text
    assert "بازار و دلار" in text
    assert "سلامت سیستم" in text
    assert "نیازمند بررسی" in text
    assert "ورودی زنده" in text
    assert "منتشرشده" in text
    assert 'id="liveFeed"' in text
    assert 'id="soundToggle"' in text
    assert 'id="panicToggle"' in text
    assert 'id="liveConnection"' in text
    assert 'rel="manifest"' in text
    assert "serviceWorker" in text


def test_panel_css_uses_doran_first_without_external_font_dependency():
    css = Path("panel/static/panel.css").read_text(encoding="utf-8")
    assert "Doran" in css
    assert "fonts.googleapis.com" not in css
    assert "@import" not in css


def test_pwa_assets_exist_and_do_not_cache_api_routes():
    manifest = Path("panel/static/manifest.webmanifest").read_text(encoding="utf-8")
    worker = Path("panel/static/sw.js").read_text(encoding="utf-8")
    assert "بی‌خبر" in manifest
    assert "standalone" in manifest
    assert "/api/" in worker
    assert "networkOnly" in worker or "startsWith('/api/')" in worker


def test_dashboard_shows_live_items_in_persian_when_pending_queue_is_empty():
    data = FakeData()
    data.files["data/panel_live_feed.json"] = [
        {
            "item_id": f"live-{index}",
            "event_id": f"event-{index}",
            "source": "Reuters",
            "source_url": f"https://example.com/{index}",
            "title": f"Live story {index}",
            "published_at_source": "2026-09-08T12:00:00+00:00",
            "discovered_at": "2026-09-08T12:01:00+00:00",
            "decision": "new_event",
            "decision_reason": "no_matching_event",
            "duplicate_of": "",
            "telegram_message_id": None,
            "panel_status": "new",
            "updated_at": "2026-09-08T12:01:00+00:00",
        }
        for index in range(5)
    ]
    app = _app(data)
    client = app.test_client()
    response = _login(client)
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ورودی زنده" in text
    assert ">5<" in text
    assert "خبر زنده صفر" in text
    assert "Live story 0" not in text
    assert "تازه" in text
    assert "نیاز به تصمیم دستی نیست" in text
    assert ">0<" in text


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
