from __future__ import annotations

from pathlib import Path

from panel.app import create_app
from panel.live_api import bp as live_api_bp
from panel.newsroom_api import bp as newsroom_api_bp
from panel.newsroom_v4_api import bp as newsroom_v4_api_bp


class FakeData:
    def __init__(self):
        self.files = {
            "data/newsroom_settings.json": {
                "auto_publish": True,
                "emergency_lock": False,
                "priority_terms": ["ایران"],
                "daily_limit": 35,
                "special_limit": 5,
            },
            "data/newsroom_v3_production_status.json": {
                "mode": "production",
                "reason": "no_safe_candidate",
                "error": "",
                "daily_limit": 35,
                "daily_published": 12,
                "daily_remaining": 23,
                "last_cycle_at": "2026-09-18T12:00:00+00:00",
            },
            "state.json": {"newsroom_engine": "v3", "telegram_state": "ok"},
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/panel_live_feed.json": [],
        }

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        del sha, message
        self.files[path] = value
        return {"sha": "next"}

    def mark_news_seen(self, key):
        del key


def _client(data: FakeData):
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": data,
            "LIVE_FEED_TRANSLATOR": lambda text: "ترجمه فارسی خبر" if text else "",
        }
    )
    app.register_blueprint(live_api_bp)
    app.register_blueprint(newsroom_api_bp)
    app.register_blueprint(newsroom_v4_api_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def test_live_feed_never_uses_raw_english_as_primary_persian_copy():
    data = FakeData()
    data.files["data/panel_live_feed.json"] = [
        {
            "item_id": "english-1",
            "news_key": "english-key",
            "source": "Reuters",
            "source_url": "https://example.com/story",
            "title": "Raw English headline must not flash in the newsroom",
            "summary": "Raw English summary",
            "panel_status": "new",
            "published_at_source": "2026-09-18T12:00:00+00:00",
            "updated_at": "2026-09-18T12:00:00+00:00",
        }
    ]

    story = _client(data).get("/api/live-feed").get_json()["items"][0]
    assert story["title"] == "عنوان فارسی در حال آماده‌سازی"
    assert story["original_title"] == "Raw English headline must not flash in the newsroom"
    assert story["original_body"] == "Raw English summary"
    assert story["needs_machine_translation"] is True
    assert story["source_url"] == "https://example.com/story"


def test_live_feed_exposes_persisted_persian_copy_without_mutating_source():
    data = FakeData()
    data.files["data/panel_live_feed.json"] = [
        {
            "item_id": "fa-1",
            "news_key": "fa-key",
            "source": "Reuters",
            "source_url": "https://example.com/fa",
            "title": "Original source title",
            "summary": "Original source summary",
            "persian_title": "تیتر نهایی فارسی",
            "persian_body": "متن نهایی فارسی",
            "final_message": "🔴 تیتر نهایی فارسی\n\nمتن نهایی فارسی",
            "panel_status": "new",
            "published_at_source": "2026-09-18T12:00:00+00:00",
            "updated_at": "2026-09-18T12:00:00+00:00",
        }
    ]

    story = _client(data).get("/api/live-feed").get_json()["items"][0]
    assert story["title"] == "تیتر نهایی فارسی"
    assert story["body"] == "متن نهایی فارسی"
    assert story["final_message"]
    assert story["original_title"] == "Original source title"
    assert story["needs_machine_translation"] is False


def test_v4_live_ui_machine_then_luna_then_prepared_publish():
    live = Path("panel/static/newsroom-live.js").read_text(encoding="utf-8")
    actions = Path("panel/static/newsroom-actions.js").read_text(encoding="utf-8")
    assert "/api/live-feed/machine-translate" in live
    assert "needs_machine_translation" in live
    assert "ترجمه ماشینی" in live
    assert "نسخه نهایی لونا" in live
    assert "متن اصلی منبع" in live
    assert "/luna" in actions
    assert "/publish-prepared" in actions


def test_editor_exposes_clickable_source_and_edits_seen_luna_copy():
    dashboard = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    editor = Path("panel/static/newsroom-editor.js").read_text(encoding="utf-8")
    assert 'id="editorSourceLink"' in dashboard
    assert 'id="editorTitle"' in dashboard
    assert 'id="editorBody"' in dashboard
    assert "sourceLink" in editor
    assert "BikhabarV4?.setLuna" in editor


def test_dashboard_has_obvious_add_source_entry_point():
    dashboard = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    assert "مدیریت منبع" in dashboard
    assert 'href="/source-manager"' in dashboard


def test_v4_drops_heavy_inline_module_previews_from_main_newsroom():
    dashboard = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    actions = Path("panel/static/newsroom-actions.js").read_text(encoding="utf-8")
    assert "data-preview-toggle" not in dashboard
    assert "air-traffic" not in dashboard
    assert "loadModulePreview" not in actions
    assert "renderModulePreview" not in actions


def test_v4_status_uses_current_v3_production_truth():
    data = FakeData()
    data.files["state.json"] = {"newsroom_engine": "v3", "telegram_state": "error"}
    data.files["data/newsroom_v3_production_status.json"].update(
        {"error": "", "publish_failed": 0, "reason": "no_safe_candidate", "daily_published": 12}
    )
    payload = _client(data).get("/api/newsroom/v4/status").get_json()
    assert payload["engine"] == "v3"
    assert payload["error"] == ""
    assert payload["daily_published"] == 12


def test_machine_translation_failure_is_visible_and_retryable():
    js = Path("panel/static/newsroom-live.js").read_text(encoding="utf-8")
    assert "خطا در آماده‌سازی ترجمه ماشینی" in js
    assert "machineFailures" in js
    assert 'data-action="machine"' in js
    assert "catch (error)" in js


def test_mobile_v4_uses_light_fixed_navigation_without_blur():
    css = Path("panel/static/newsroom-v4.css").read_text(encoding="utf-8")
    assert ".nr-mobile-nav" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "backdrop-filter:none!important" in css
    assert "--v4-bg:#f4f7fb" in css


def test_production_wsgi_wires_machine_translator():
    wsgi = Path("panel/wsgi.py").read_text(encoding="utf-8")
    assert "from src.services import translate_to_fa" in wsgi
    assert 'config["LIVE_FEED_TRANSLATOR"] = translate_to_fa' in wsgi
