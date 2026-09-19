from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from panel.app import create_app


class MemoryData:
    def __init__(self, live):
        self.mapping = {
            "data/panel_live_feed.json": deepcopy(live),
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "state.json": {"daily_published": 0, "daily_limit": 35},
        }

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), None

    def write_json(self, path, value, sha, message):
        del sha, message
        self.mapping[path] = deepcopy(value)
        return "memory-sha"


def _dashboard_html(live):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "WTF_CSRF_ENABLED": False,
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": MemoryData(live),
        }
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    response = client.get("/")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_untranslated_english_story_is_not_rendered_as_dashboard_card():
    html = _dashboard_html(
        [
            {
                "id": "story-pending",
                "item_id": "story-pending",
                "source": "Reuters",
                "original_title": "A new English headline awaiting translation",
                "original_summary": "An English body awaiting translation.",
                "panel_status": "new",
                "updated_at": "2026-09-19T12:00:00+00:00",
            }
        ]
    )

    assert 'data-story-id="story-pending"' not in html
    assert "عنوان فارسی در حال آماده‌سازی" not in html


def test_machine_persian_story_is_visible_immediately_with_direct_publish():
    html = _dashboard_html(
        [
            {
                "id": "story-ready",
                "item_id": "story-ready",
                "source": "Reuters",
                "original_title": "A translated headline",
                "original_summary": "A translated body.",
                "persian_title": "این تیتر از قبل به فارسی ترجمه شده است",
                "persian_body": "متن فارسی آماده بررسی و انتشار است.",
                "machine_translation_status": "passed",
                "panel_status": "new",
                "updated_at": "2026-09-19T12:00:00+00:00",
            }
        ]
    )

    assert 'data-story-id="story-ready"' in html
    assert "این تیتر از قبل به فارسی ترجمه شده است" in html
    assert "انتشار مستقیم" in html


def test_dashboard_javascript_localizes_before_showing_new_cards():
    js = Path("panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")

    assert "function isVisibleStory" in js
    assert "items.filter(item => isVisibleStory(item))" in js
    assert "عنوان فارسی در حال آماده‌سازی" not in js
    assert "ترجمه ماشینی در حال آماده‌سازی" not in js

    refresh = js[js.index("async function refreshLiveFeed"):]
    localize_at = refresh.index("await localizePending")
    sync_at = refresh.index("syncLiveCards")
    assert localize_at < sync_at
