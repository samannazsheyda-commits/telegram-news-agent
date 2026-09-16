from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from panel.app import create_app
from panel.command_center import bp as command_center_bp
from panel.newsroom_api import bp as newsroom_api_bp


class FakeData:
    def __init__(self):
        self.files = {
            "data/newsroom_settings.json": {
                "auto_publish": True,
                "emergency_lock": False,
                "quiet_mode": False,
                "quiet_start": "00:00",
                "quiet_end": "07:00",
                "freshness_hours": 3,
                "priority_terms": ["تنگه هرمز", "موشک"],
            },
            "data/newsroom_v3_production_status.json": {
                "mode": "production",
                "reason": "published",
                "error": "",
                "sources_ok": 6,
                "sources_failed": 0,
                "items_fetched": 188,
                "processed": 188,
                "ready": 27,
                "waiting": 32,
                "rejected": 125,
                "duplicates": 4,
                "published": 1,
                "telegram_writes": 1,
                "publish_failed": 0,
                "story_id": "story-v3",
                "telegram_message_id": 1457,
                "last_cycle_at": "2026-09-14T10:45:23+00:00",
                "last_published_at": "2026-09-14T10:45:23+00:00",
            },
            "state.json": {
                "newsroom_engine": "v3",
                "last_cycle_at": "2026-09-14T10:45:23+00:00",
                "telegram_state": "ok",
            },
            "data/panel_live_feed.json": [
                {
                    "id": "live-1",
                    "item_id": "live-1",
                    "news_key": "news-live-1",
                    "source": "Reuters",
                    "source_url": "https://example.com/live-1",
                    "original_title": "Original Reuters headline",
                    "original_summary": "Original Reuters body",
                    "persian_title": "تیتر فارسی زنده",
                    "persian_body": "متن کوتاه خبر",
                    "panel_status": "new",
                    "source_priority": "high",
                    "discovered_at": "2026-09-14T10:44:00+00:00",
                }
            ],
            "data/editorial_queue.json": [{"id": "review-1", "status": "pending"}],
            "data/editorial_history.json": [
                {"id": "pub-1", "status": "published_auto", "decision_at": "2026-09-14T09:00:00+00:00"},
                {"id": "rej-1", "status": "rejected_manual", "decision_at": "2026-09-14T09:30:00+00:00"},
            ],
            "panel_results/cmd-done.json": {
                "command_id": "cmd-done",
                "status": "succeeded",
                "message": "انجام شد",
            },
            "panel_results/cmd-ambiguous.json": {
                "command_id": "cmd-ambiguous",
                "status": "ambiguous",
                "message": "وضعیت ارسال تلگرام نامشخص است",
            },
        }
        self.commands: list[dict] = []

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        if path.startswith("panel_commands/"):
            self.commands.append(dict(value))
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        return None


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    return match.group(1)


def _app(data: FakeData):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": generate_password_hash("pass"),
            "DATA_BACKEND": data,
            "LIVE_FEED_TRANSLATOR": lambda text: text,
        }
    )
    app.register_blueprint(command_center_bp)
    app.register_blueprint(newsroom_api_bp)
    return app


def _login(client) -> str:
    page = client.get("/login")
    token = _csrf(page.get_data(as_text=True))
    client.post("/login", data={"password": "pass", "csrf_token": token})
    dashboard = client.get("/").get_data(as_text=True)
    meta = re.search(r'<meta name="csrf-token" content="([^"]+)"', dashboard)
    assert meta
    return meta.group(1)


def test_snapshot_requires_admin_session():
    response = _app(FakeData()).test_client().get("/api/newsroom/snapshot")
    assert response.status_code == 401


def test_snapshot_is_v3_first_and_reports_real_production_status():
    data = FakeData()
    client = _app(data).test_client()
    _login(client)

    response = client.get("/api/newsroom/snapshot")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["ok"] is True
    assert payload["engine"] == "v3"
    assert payload["publishing"] is True
    assert payload["v3"]["mode"] == "production"
    assert payload["v3"]["reason"] == "published"
    assert payload["v3"]["error"] == ""
    assert payload["v3"]["sources_ok"] == 6
    assert payload["v3"]["sources_failed"] == 0
    assert payload["v3"]["items_fetched"] == 188
    assert payload["v3"]["published"] == 1
    assert payload["v3"]["publish_failed"] == 0
    assert payload["v3"]["telegram_message_id"] == 1457
    assert payload["counts"]["live"] == 1
    assert payload["counts"]["review"] == 1
    assert payload["live"][0]["id"] == "live-1"
    assert payload["settings"]["priority_terms"] == ["تنگه هرمز", "موشک"]
    assert isinstance(payload["fingerprint"], str) and len(payload["fingerprint"]) >= 12
    serialized = str(payload).lower()
    assert "telegram_bot_token" not in serialized
    assert "password" not in serialized


def test_newsroom_action_aliases_use_local_command_queue_and_stable_shapes():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)

    scan = client.post("/api/newsroom/scan", headers={"X-CSRFToken": csrf})
    assert scan.status_code == 202
    assert scan.get_json()["status"] == "queued"
    assert data.commands[-1]["action"] == "refresh"

    review = client.post("/api/newsroom/live/live-1/review", headers={"X-CSRFToken": csrf})
    assert review.status_code == 200
    assert review.get_json()["status"] == "succeeded"

    rejected = client.post("/api/newsroom/live/live-1/reject", headers={"X-CSRFToken": csrf})
    assert rejected.status_code == 200
    assert rejected.get_json()["status"] == "succeeded"


def test_newsroom_command_result_preserves_ambiguous_state():
    data = FakeData()
    client = _app(data).test_client()
    _login(client)

    response = client.get("/api/newsroom/command/cmd-ambiguous")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ambiguous"
    assert "نامشخص" in payload["message"]


def test_inline_editor_save_persists_edited_persian_copy_to_review_queue():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)

    response = client.post(
        "/api/newsroom/live/live-1/review",
        headers={"X-CSRFToken": csrf},
        json={"title": "تیتر نهایی ویرایش‌شده", "body": "متن نهایی ویرایش‌شده برای بررسی."},
    )

    assert response.status_code == 200
    queued = next(row for row in data.files["data/editorial_queue.json"] if row.get("id") == "live-1")
    assert queued["persian_title"] == "تیتر نهایی ویرایش‌شده"
    assert queued["persian_body"] == "متن نهایی ویرایش‌شده برای بررسی."
    assert data.commands == []


def test_publish_queues_original_source_for_luna_not_editor_copy():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)

    response = client.post(
        "/api/newsroom/live/live-1/publish",
        headers={"X-CSRFToken": csrf},
        json={"title": "تیتر ویرایش‌شده برای انتشار", "body": "متن ویرایش‌شده‌ای که نباید جای منبع را بگیرد."},
    )

    assert response.status_code == 202
    command = data.commands[-1]
    assert command["action"] == "v3_publish"
    assert command["original_title"] == "Original Reuters headline"
    assert command["original_body"] == "Original Reuters body"
    assert command["source"] == "Reuters"
    assert command["source_url"] == "https://example.com/live-1"
    assert "title" not in command
    assert "body" not in command
    queued = next(row for row in data.files["data/editorial_queue.json"] if row.get("id") == "live-1")
    assert queued["original_title"] == command["original_title"]
    assert queued["original_summary"] == command["original_body"]


def test_publish_ignores_untrusted_editor_payload_and_review_rejects_oversized_copy():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)

    publish = client.post(
        "/api/newsroom/live/live-1/publish",
        headers={"X-CSRFToken": csrf},
        json={"title": "Final English title", "body": "متن"},
    )
    assert publish.status_code == 202
    assert data.commands[-1]["original_title"] == "Original Reuters headline"
    assert "title" not in data.commands[-1]

    oversized = client.post(
        "/api/newsroom/live/live-1/review",
        headers={"X-CSRFToken": csrf},
        json={"title": "خ" * 281, "body": "متن"},
    )
    assert oversized.status_code == 400
    assert oversized.get_json()["error"] == "invalid_editor_payload"
