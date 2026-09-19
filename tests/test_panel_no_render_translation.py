from __future__ import annotations

from pathlib import Path

from panel.app import create_app


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
                    "source_display": "رویترز",
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


def test_dashboard_get_never_calls_translation_backend_and_hides_unready_story_completely():
    data = FakeData()
    calls: list[str] = []

    def forbidden_translator(text: str) -> str:
        calls.append(text)
        return "ترجمه‌ای که نباید در GET اجرا شود"

    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": data,
            "LIVE_FEED_TRANSLATOR": forbidden_translator,
        }
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True

    response = client.get("/")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert calls == []
    assert "Raw English headline" not in text
    assert "Raw English summary" not in text
    assert "عنوان فارسی در حال آماده‌سازی" not in text
    assert 'data-story-id="english-1"' not in text


def test_v41_ui_translates_only_on_explicit_luna_action_and_rejects_without_blocking():
    js = Path("panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")

    assert "/api/panel/luna/translate-story/" in js
    assert "/api/panel/machine-preview/" not in js
    assert "IntersectionObserver" not in js
    assert "translateWithLuna" in js
    assert "/api/newsroom/live/${encodeURIComponent(id)}/reject" in js
    assert "/api/panel/luna/block-story/" not in js
    assert "reject-block" not in js
