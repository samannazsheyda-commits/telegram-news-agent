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
            "data/custom_sources.json": [],
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
    assert "newsroom-v4-pages.css" in html
    assert "newsroom-v4.js" in html
    for legacy in ("newsroom-shell.css", "newsroom-final.css", "newsroom-ui.js", "newsroom-live.js", "newsroom-actions.js", "newsroom-editor.js"):
        assert legacy not in html
    assert 'data-newsroom-shell="v4"' in html


def test_mobile_first_navigation_and_health_status_are_immediately_available():
    html = _dashboard_html()
    assert 'class="v4-mobile-nav"' in html
    assert 'id="agentHealth"' in html
    assert 'id="lunaHealth"' in html
    assert 'id="telegramHealth"' in html
    assert 'id="lastCycle"' in html
    for label in ("داشبورد", "ورودی", "بررسی", "لونا", "بیشتر"):
        assert label in html


def test_dashboard_is_summary_first_instead_of_rendering_story_cards():
    html = _dashboard_html()
    assert 'id="incomingCount"' in html
    assert 'href="/incoming"' in html
    assert 'data-story-id="live-1"' not in html
    assert "تیتر مهم برای تست اتاق خبر" not in html


def test_sensitive_editorial_actions_live_in_preview_safe_review_surface():
    review = Path("panel/templates/review_edit.html").read_text(encoding="utf-8")
    assert 'id="v4PublishFinal"' in review
    assert 'id="v4RejectFinal"' in review
    assert "تأیید انتشار" in review
    assert "/publish-final" in review
    assert "Luna دوباره اجرا نمی‌شود" in review


def test_v4_runtime_replaces_legacy_live_bundle_and_hides_secrets():
    html = _dashboard_html()
    assert "newsroom-v4.js" in html
    for asset in ("newsroom-ui.js", "newsroom-live.js", "newsroom-actions.js", "newsroom-editor.js", "static/live.js"):
        assert asset not in html
    assert "TELEGRAM_BOT_TOKEN" not in html
