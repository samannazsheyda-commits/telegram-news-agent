from __future__ import annotations

import re
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from panel.app import create_app
from panel.live_api import bp as live_api_bp


class FakeData:
    def __init__(self, rows):
        self.rows = rows

    def read_json(self, path, default):
        if path == "data/panel_live_feed.json":
            return self.rows, "sha"
        return default, "sha"

    def write_json(self, path, value, sha, message):
        self.rows = value
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        return None


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    return match.group(1)


def _client(rows):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "PANEL_PASSWORD_HASH": generate_password_hash("pass"),
        "DATA_BACKEND": FakeData(rows),
        "LIVE_FEED_TRANSLATOR": lambda text: text,
    })
    app.register_blueprint(live_api_bp)
    client = app.test_client()
    page = client.get("/login")
    token = _csrf(page.get_data(as_text=True))
    client.post("/login", data={"password": "pass", "csrf_token": token})
    return client


def test_api_is_persian_first_and_keeps_original_hidden_field():
    rows = [{
        "item_id": "1",
        "source": "Reuters",
        "source_url": "https://reuters.example/1",
        "title": "Iran says airspace remains open",
        "persian_title": "ایران اعلام کرد حریم هوایی باز است",
        "published_at_source": "2026-09-09T12:30:00+00:00",
        "discovered_at": "2026-09-09T12:30:04+00:00",
        "updated_at": "2026-09-09T12:30:05+00:00",
        "panel_status": "new",
        "decision_reason": "eligible",
    }]
    payload = _client(rows).get("/api/live-feed").get_json()
    item = payload["items"][0]
    assert item["title_fa"] == "ایران اعلام کرد حریم هوایی باز است"
    assert item["original_title"] == "Iran says airspace remains open"
    assert item["title"] == item["title_fa"]
    assert item["source_time_iso"] == "2026-09-09T12:30:00+00:00"
    assert item["arrival_time_iso"] == "2026-09-09T12:30:04+00:00"
    assert "شهریور" in item["source_time_fa"]
    assert "شهریور" in item["arrival_time_fa"]
    assert isinstance(item["age_seconds"], int)


def test_api_never_exposes_raw_english_as_default_title():
    rows = [{
        "item_id": "1",
        "source": "Reuters",
        "source_url": "https://reuters.example/1",
        "title": "Iran says airspace remains open",
        "published_at_source": "2026-09-09T12:30:00+00:00",
        "discovered_at": "2026-09-09T12:30:04+00:00",
        "updated_at": "2026-09-09T12:30:05+00:00",
        "panel_status": "new",
        "decision_reason": "eligible",
    }]
    item = _client(rows).get("/api/live-feed").get_json()["items"][0]
    assert item["title_fa"] == "عنوان فارسی در حال آماده‌سازی"
    assert item["original_title"] == "Iran says airspace remains open"


def test_question_and_article_rows_are_removed_from_primary_feed():
    base = {
        "source": "Example",
        "source_url": "https://example.com/story",
        "published_at_source": "2026-09-09T12:30:00+00:00",
        "discovered_at": "2026-09-09T12:30:04+00:00",
        "updated_at": "2026-09-09T12:30:05+00:00",
        "panel_status": "new",
    }
    rows = [
        dict(base, item_id="q", title="Why is Iran changing its strategy?", persian_title="چرا ایران راهبرد خود را تغییر می‌دهد؟"),
        dict(base, item_id="a", title="Analysis: What the war means for markets", persian_title="تحلیل: جنگ چه معنایی برای بازار دارد"),
        dict(base, item_id="n", title="Iranian air defense intercepted a drone near Tehran", persian_title="پدافند هوایی ایران یک پهپاد را نزدیک تهران رهگیری کرد"),
    ]
    payload = _client(rows).get("/api/live-feed").get_json()
    assert [item["id"] for item in payload["items"]] == ["n"]
