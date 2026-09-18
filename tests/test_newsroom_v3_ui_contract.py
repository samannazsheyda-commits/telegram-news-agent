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
                    "source_display": "رویترز",
                    "source_url": "https://example.com/1",
                    "original_title": "Important original newsroom test headline",
                    "original_summary": "Original source summary for the newsroom test.",
                    "persian_title": "تیتر قدیمی که نباید با ترجمه ماشینی قاطی شود",
                    "persian_body": "متن قدیمی که نباید به‌عنوان ترجمه ماشینی نشان داده شود",
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


def test_dashboard_uses_single_v4_newsroom_shell_without_legacy_style_stack():
    html = _dashboard_html()
    assert "newsroom-v4.css" in html
    assert "newsroom-shell.css" not in html
    assert "newsroom-final.css" not in html
    assert "newsroom-nav-v2.css" not in html
    assert "newsroom-compact.css" not in html
    assert 'data-newsroom-shell="v4"' in html


def test_mobile_first_navigation_and_health_are_immediately_available():
    html = _dashboard_html()
    assert 'class="v4-mobile-nav"' in html
    assert "سلامت سیستم" in html
    assert "Luna" in html
    for label in ("داشبورد", "ورودی", "بررسی", "کنترل"):
        assert label in html


def test_server_rendered_story_card_requires_luna_preview_before_publish():
    html = _dashboard_html()
    assert 'data-story-id="live-1"' in html
    assert 'data-v4-action="send-luna"' in html
    assert 'data-v4-action="reject"' in html
    assert 'data-v4-action="publish-final"' not in html
    assert 'data-action="publish"' not in html
    assert "Important original newsroom test headline" in html
    assert "ترجمه ماشینی هنوز آماده نیست" in html
    assert "تیتر قدیمی که نباید با ترجمه ماشینی قاطی شود" not in html
    assert "رویترز" in html


def test_sensitive_actions_have_v4_confirmation_surface():
    html = _dashboard_html()
    assert 'id="v4ConfirmDialog"' in html
    assert 'id="v4ConfirmAccept"' in html
    assert "newsroom-v4.js" in html


def test_dashboard_loads_only_v4_dashboard_modules():
    html = _dashboard_html()
    assert "newsroom-v4.js" in html
    assert "newsroom-v4-dashboard.js" in html
    for legacy in ("newsroom-ui.js", "newsroom-live.js", "newsroom-actions.js", "newsroom-editor.js", "static/live.js"):
        assert legacy not in html
    assert "TELEGRAM_BOT_TOKEN" not in html
