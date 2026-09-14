from __future__ import annotations

from panel.app import create_app


class FakeData:
    def __init__(self):
        self.files = {
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/panel_live_feed.json": [
                {
                    "id": "live-1",
                    "item_id": "live-1",
                    "news_key": "key-1",
                    "source": "Reuters",
                    "source_url": "https://example.com/1",
                    "persian_title": "تیتر مهم برای تست اتاق خبر",
                    "persian_body": "متن خلاصه خبر برای تصمیم سردبیری.",
                    "panel_status": "new",
                    "source_priority": "high",
                    "discovered_at": "2026-09-14T11:50:00+00:00",
                }
            ],
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


def test_dashboard_uses_single_v3_newsroom_shell_without_legacy_style_stack():
    html = _dashboard_html()
    assert "newsroom-shell.css" in html
    assert "light-newsroom.css" not in html
    assert "newsroom.css" not in html
    assert "newsroom-nav-v2.css" not in html
    assert "newsroom-compact.css" not in html
    assert 'data-newsroom-shell="v3"' in html


def test_mobile_first_navigation_and_v3_status_are_immediately_available():
    html = _dashboard_html()
    assert 'id="newsroomStatusBar"' in html
    assert 'id="engineState"' in html
    assert 'id="telegramState"' in html
    assert 'id="publishingState"' in html
    assert 'id="lastCycleAt"' in html
    assert 'id="mobileBottomNav"' in html
    for label in ("اتاق خبر", "بررسی", "منتشرشده", "منابع"):
        assert label in html


def test_server_rendered_story_card_exposes_direct_editorial_actions():
    html = _dashboard_html()
    assert 'data-story-id="live-1"' in html
    assert 'data-action="publish"' in html
    assert 'data-action="edit"' in html
    assert 'data-action="reject"' in html
    assert 'data-action="source"' in html
    assert "تیتر مهم برای تست اتاق خبر" in html
    assert "Reuters" in html


def test_sensitive_actions_have_confirmation_and_inline_editor_hooks():
    html = _dashboard_html()
    assert 'id="confirmSheet"' in html
    assert 'id="confirmAccept"' in html
    assert 'id="editorSheet"' in html
    assert 'id="editorTitle"' in html
    assert 'id="editorBody"' in html
    assert 'data-confirm-action="publishing"' in html


def test_dashboard_loads_small_newsroom_modules_instead_of_legacy_live_bundle():
    html = _dashboard_html()
    for asset in (
        "newsroom-ui.js",
        "newsroom-live.js",
        "newsroom-actions.js",
        "newsroom-editor.js",
    ):
        assert asset in html
    assert "static/live.js" not in html
    assert "TELEGRAM_BOT_TOKEN" not in html
