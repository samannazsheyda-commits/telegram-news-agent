from __future__ import annotations

from copy import deepcopy

from panel.app import create_app
from panel.v4 import bp as panel_v4_bp


class MemoryData:
    def __init__(self, mapping: dict[str, object]):
        self.mapping = deepcopy(mapping)
        self.writes: list[tuple[str, object]] = []

    def read_json(self, path: str, default):
        return deepcopy(self.mapping.get(path, default)), None

    def write_json(self, path: str, value, sha, message: str):
        self.mapping[path] = deepcopy(value)
        self.writes.append((path, deepcopy(value)))
        return "memory-sha"

    def mark_news_seen(self, key: str):
        return None


def _make_client(*, finalizer=None, machine_translator=None):
    data = MemoryData(
        {
            "data/panel_live_feed.json": [
                {
                    "id": "story-1",
                    "news_key": "news-1",
                    "source": "Reuters",
                    "source_url": "https://example.com/1",
                    "original_title": "Iran announces a new measure",
                    "original_summary": "Officials announced a concrete new measure today.",
                    "panel_status": "new",
                    "updated_at": "2026-09-18T14:00:00+00:00",
                }
            ],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/newsroom_settings.json": {"auto_publish": True},
            "state.json": {"daily_limit": 35, "daily_published": 12},
        }
    )
    config = {
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "WTF_CSRF_ENABLED": False,
        "DATA_BACKEND": data,
    }
    if finalizer is not None:
        config["PANEL_LUNA_FINALIZER"] = finalizer
    if machine_translator is not None:
        config["PANEL_MACHINE_TRANSLATOR"] = machine_translator
    app = create_app(config)
    app.register_blueprint(panel_v4_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client, data


def test_luna_preview_is_saved_without_publishing():
    def finalizer(row: dict) -> dict:
        assert row["id"] == "story-1"
        return {
            "decision": "PUBLISH",
            "importance": 8.7,
            "reason_fa": "توسعه جدید و مهم",
            "title_fa": "ایران اقدام تازه‌ای را اعلام کرد",
            "body_fa": "مقام‌ها امروز از یک اقدام مشخص تازه خبر دادند",
            "confidence": 0.94,
        }

    client, data = _make_client(finalizer=finalizer)
    response = client.post("/api/panel/luna/preview/story-1")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["preview"]["decision"] == "PUBLISH"
    assert payload["preview"]["title_fa"] == "ایران اقدام تازه‌ای را اعلام کرد"
    assert data.mapping["data/panel_luna_previews.json"][0]["story_id"] == "story-1"
    assert not any(path.startswith("panel_commands/") for path, _ in data.writes)


def test_publish_requires_saved_luna_preview():
    client, _ = _make_client()
    response = client.post("/api/panel/luna/publish/story-1")
    payload = response.get_json()

    assert response.status_code == 409
    assert payload["error"] == "luna_preview_required"


def test_publish_after_preview_uses_existing_v3_publish_command_shape():
    def finalizer(row: dict) -> dict:
        return {
            "decision": "SPECIAL",
            "importance": 9.4,
            "reason_fa": "تحول فوری",
            "title_fa": "تیتر نهایی لونا",
            "body_fa": "متن نهایی لونا",
            "confidence": 0.98,
        }

    client, data = _make_client(finalizer=finalizer)
    assert client.post("/api/panel/luna/preview/story-1").status_code == 200

    response = client.post("/api/panel/luna/publish/story-1")
    payload = response.get_json()

    assert response.status_code == 202
    assert payload["ok"] is True
    command_path = next(path for path, _ in data.writes if path.startswith("panel_commands/"))
    command = data.mapping[command_path]
    assert command["action"] == "v3_publish"
    assert command["item_id"] == "story-1"
    assert command["title"] == "تیتر نهایی لونا"
    assert command["body"] == "متن نهایی لونا"


def test_machine_preview_uses_lightweight_injected_translator():
    calls: list[str] = []

    def translator(text: str) -> str:
        calls.append(text)
        return "ترجمه سبک پنل"

    client, _ = _make_client(machine_translator=translator)
    response = client.post("/api/panel/machine-preview/story-1")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["preview"] == "ترجمه سبک پنل"
    assert calls and "Iran announces" in calls[0]


def test_rejected_luna_preview_cannot_be_published():
    def finalizer(row: dict) -> dict:
        return {
            "decision": "REJECT",
            "importance": 2.0,
            "reason_fa": "ارزش خبری کافی ندارد",
            "title_fa": "",
            "body_fa": "",
            "confidence": 0.9,
        }

    client, _ = _make_client(finalizer=finalizer)
    assert client.post("/api/panel/luna/preview/story-1").status_code == 200
    response = client.post("/api/panel/luna/publish/story-1")
    assert response.status_code == 409
    assert response.get_json()["error"] == "luna_preview_not_publishable"
