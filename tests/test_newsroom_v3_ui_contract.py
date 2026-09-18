from __future__ import annotations

from panel.app import create_app


class FakeData:
    def __init__(self):
        self.files = {
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/panel_live_feed.json": [],
            "data/newsroom_settings.json": {"daily_limit": 35, "special_limit": 5},
            "data/newsroom_v3_production_status.json": {"daily_published": 12, "ready": 3, "waiting": 4},
            "state.json": {"newsroom_engine": "v3"},
        }

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        del sha, message
        self.files[path] = value
        return {"sha": "next"}

    def mark_news_seen(self, key):
        return None


def _dashboard_html() -> str:
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": FakeData(),
            "LIVE_FEED_TRANSLATOR": lambda text: text,
        }
    )
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = True
    response = client.get("/")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_dashboard_uses_v4_override_without_legacy_bundles():
    html = _dashboard_html()
    assert "newsroom-shell.css" in html
    assert "newsroom-v4.css" in html
    assert "light-newsroom.css" not in html
    assert "newsroom-nav-v2.css" not in html
    assert 'data-newsroom-shell="v3"' in html


def test_navigation_and_daily_status_are_immediately_available():
    html = _dashboard_html()
    assert 'id="newsroomStatusBar"' in html
    assert 'id="engineState"' in html
    assert 'id="publishedCount"' in html
    assert 'id="dailyLimitLabel"' in html
    assert 'id="dailyRemainingLabel"' in html
    assert 'id="lastCycleAt"' in html
    assert 'id="mobileBottomNav"' in html
    for label in ("اتاق خبر", "بررسی", "منتشرشده", "منابع"):
        assert label in html


def test_live_feed_is_client_rendered_for_fast_first_paint():
    html = _dashboard_html()
    assert 'id="liveFeed"' in html
    assert "در حال دریافت تازه‌ترین خبرها" in html
    assert 'data-story-id="live-1"' not in html
    assert "newsroom-live.js" in html


def test_sensitive_actions_have_confirmation_and_luna_editor_hooks():
    html = _dashboard_html()
    assert 'id="confirmSheet"' in html
    assert 'id="confirmAccept"' in html
    assert 'id="editorSheet"' in html
    assert 'id="editorTitle"' in html
    assert 'id="editorBody"' in html
    assert 'id="editorSourceLink"' in html


def test_dashboard_loads_small_v4_modules_instead_of_legacy_live_bundle():
    html = _dashboard_html()
    for asset in ("newsroom-ui.js", "newsroom-live.js", "newsroom-actions.js", "newsroom-editor.js"):
        assert asset in html
    assert "static/live.js" not in html
    assert "TELEGRAM_BOT_TOKEN" not in html
