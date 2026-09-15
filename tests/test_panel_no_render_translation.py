from __future__ import annotations

from pathlib import Path

from panel.app import create_app
from panel.live_api import bp as live_api_bp


class FakeData:
    def __init__(self):
        self.files = {
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/panel_live_feed.json": [
                {
                    "item_id": "english-1",
                    "news_key": "english-key",
                    "source": "Reuters",
                    "source_url": "https://example.com/story",
                    "title": "Raw English headline must not trigger translation during dashboard render",
                    "summary": "Raw English summary",
                    "panel_status": "new",
                    "published_at_source": "2026-09-15T19:00:00+00:00",
                    "updated_at": "2026-09-15T19:00:00+00:00",
                }
            ],
            "state.json": {"newsroom_engine": "v3", "telegram_state": "ok"},
        }

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        del sha, message
        self.files[path] = value
        return {"sha": "next"}

    def mark_news_seen(self, key):
        del key


def _client(data: FakeData, translator):
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": data,
            "LIVE_FEED_TRANSLATOR": translator,
        }
    )
    app.register_blueprint(live_api_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def test_dashboard_get_never_calls_translation_backend():
    data = FakeData()
    calls: list[str] = []

    def forbidden_translator(text: str) -> str:
        calls.append(text)
        return "ترجمه‌ای که نباید در GET اجرا شود"

    client = _client(data, forbidden_translator)
    response = client.get("/")

    assert response.status_code == 200
    assert calls == []
    assert "Raw English headline" not in response.get_data(as_text=True)


def test_localize_endpoint_enqueues_background_command_without_translation():
    data = FakeData()
    calls: list[str] = []

    def forbidden_translator(text: str) -> str:
        calls.append(text)
        return "ترجمه‌ای که نباید در Gunicorn اجرا شود"

    client = _client(data, forbidden_translator)
    response = client.post("/api/live-feed/localize", json={"ids": ["english-1"]})

    assert response.status_code == 200
    assert calls == []
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["status"] == "queued"
    assert payload["queued_ids"] == ["english-1"]
    commands = [value for path, value in data.files.items() if path.startswith("panel_commands/")]
    assert len(commands) == 1
    assert commands[0]["action"] == "live_localize"
    assert commands[0]["item_id"] == "english-1"


def test_live_ui_auto_queues_missing_localization_after_snapshot_render():
    js = Path("panel/static/newsroom-live.js").read_text(encoding="utf-8")

    assert "retry-localization" in js
    assert "void localizeMissing(currentStories);" in js
    assert "slice(0, 2)" in js
