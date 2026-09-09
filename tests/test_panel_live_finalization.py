from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from panel.app import create_app
from panel.command_center import bp as command_center_bp
from panel.live_api import bp as live_api_bp


class FakeData:
    def __init__(self):
        self.files = {
            "data/newsroom_settings.json": {"auto_publish": True, "emergency_lock": False, "freshness_hours": 3},
            "data/panel_live_feed.json": [
                {
                    "item_id": "n1",
                    "source": "Reuters",
                    "source_url": "https://example.com/n1",
                    "title": "Iran launches a missile",
                    "summary": "The missile was launched toward a military target.",
                    "published_at_source": "2026-09-09T21:00:00+00:00",
                    "updated_at": "2026-09-09T21:00:01+00:00",
                    "panel_status": "new",
                }
            ],
            "data/editorial_queue.json": [],
        }
        self.commands = []

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        if path.startswith("panel_commands/"):
            self.commands.append(value)
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        return None


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    return match.group(1)


def _app(data: FakeData):
    translations = {
        "Iran launches a missile": "ایران یک موشک شلیک کرد",
        "The missile was launched toward a military target.": "این موشک به سوی یک هدف نظامی شلیک شد.",
    }
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "PANEL_PASSWORD_HASH": generate_password_hash("pass"),
        "DATA_BACKEND": data,
        "LIVE_FEED_TRANSLATOR": lambda text: translations.get(text, text),
    })
    app.register_blueprint(command_center_bp)
    app.register_blueprint(live_api_bp)
    return app


def _login(client) -> str:
    page = client.get("/login").get_data(as_text=True)
    token = _csrf(page)
    client.post("/login", data={"password": "pass", "csrf_token": token})
    dashboard = client.get("/").get_data(as_text=True)
    meta = re.search(r'<meta name="csrf-token" content="([^"]+)"', dashboard)
    assert meta
    return meta.group(1)


def test_live_feed_get_stays_fast_and_marks_missing_persian_translation():
    data = FakeData(); client = _app(data).test_client(); _login(client)
    payload = client.get("/api/live-feed").get_json()
    assert payload["items"][0]["title"] == "عنوان فارسی در حال آماده‌سازی"
    assert payload["items"][0]["needs_localization"] is True


def test_live_localize_endpoint_returns_persian_title_body_and_final_message():
    data = FakeData(); client = _app(data).test_client(); csrf = _login(client)
    response = client.post("/api/live-feed/localize", json={"ids": ["n1"]}, headers={"X-CSRFToken": csrf})
    assert response.status_code == 200
    item = response.get_json()["items"][0]
    assert item["id"] == "n1"
    assert item["title"] == "ایران یک موشک شلیک کرد"
    assert item["body"] == "این موشک به سوی یک هدف نظامی شلیک شد."
    assert "ایران یک موشک شلیک کرد" in item["final_message"]
    assert "Reuters" not in item["final_message"]


def test_preview_generation_endpoint_queues_non_publishing_preview_command():
    data = FakeData(); client = _app(data).test_client(); csrf = _login(client)
    expected = {
        "weather": "weather_preview",
        "air-traffic": "air_traffic_preview",
        "tanker": "tanker_preview",
        "market": "market_preview",
    }
    for module, action in expected.items():
        response = client.post(f"/api/command-center/module/{module}/preview", headers={"X-CSRFToken": csrf})
        assert response.status_code == 202
        assert data.commands[-1]["action"] == action
