from __future__ import annotations

import re
from pathlib import Path

from panel.app import create_app
from panel.live_api import bp as live_api_bp
from panel.newsroom_api import bp as newsroom_api_bp

# Live production screenshot regression coverage. Keep these assertions behavior-focused.


class FakeData:
    def __init__(self):
        self.files = {
            "data/newsroom_settings.json": {
                "auto_publish": True,
                "emergency_lock": False,
                "priority_terms": ["ایران"],
            },
            "data/newsroom_v3_production_status.json": {
                "mode": "production",
                "reason": "no_safe_candidate",
                "error": "",
                "last_cycle_at": "2026-09-14T12:00:00+00:00",
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
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def test_v3_snapshot_never_uses_raw_english_as_primary_display_copy():
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
            "published_at_source": "2026-09-14T12:00:00+00:00",
            "updated_at": "2026-09-14T12:00:00+00:00",
        }
    ]

    payload = _client(data).get("/api/newsroom/snapshot").get_json()
    story = payload["live"][0]

    assert story["title"] == "عنوان فارسی در حال آماده‌سازی"
    assert story["original_title"] == "Raw English headline must not flash in the newsroom"
    assert story["original_body"] == "Raw English summary"
    assert story["needs_localization"] is True
    assert story["source_url"] == "https://example.com/story"
    assert "Raw English headline" not in story["title"]


def test_v3_snapshot_exposes_persisted_final_telegram_copy_for_editing():
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
            "final_message": "🔴 تیتر نهایی فارسی\n\nمتن نهایی فارسی\n\nمنبع: https://example.com/fa",
            "panel_status": "new",
            "published_at_source": "2026-09-14T12:00:00+00:00",
            "updated_at": "2026-09-14T12:00:00+00:00",
        }
    ]

    story = _client(data).get("/api/newsroom/snapshot").get_json()["live"][0]

    assert story["title"] == "تیتر نهایی فارسی"
    assert story["body"] == "متن نهایی فارسی"
    assert "تیتر نهایی فارسی" in story["final_message"]
    assert story["original_title"] == "Original source title"
    assert story["source_url"] == "https://example.com/fa"
    assert story["needs_localization"] is False


def test_new_live_ui_localizes_missing_copy_and_shows_final_telegram_output():
    js = Path("panel/static/newsroom-live.js").read_text(encoding="utf-8")

    assert "/api/live-feed/localize" in js
    assert "needs_localization" in js
    assert "final_message" in js
    assert "نسخه نهایی تلگرام" in js
    assert "متن اصلی منبع" in js


def test_v4_editorial_surfaces_expose_clickable_source_link():
    incoming = Path("panel/templates/incoming.html").read_text(encoding="utf-8")
    review = Path("panel/templates/review_edit.html").read_text(encoding="utf-8")

    for template in (incoming, review):
        assert "item.source_url" in template
        assert 'target="_blank"' in template
        assert 'rel="noopener"' in template
    assert "باز کردن منبع" in incoming
    assert "باز کردن منبع" in review


def test_dashboard_has_obvious_add_source_entry_point():
    dashboard = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")

    assert "افزودن منبع" in dashboard
    assert 'href="/source-manager"' in dashboard


def test_module_preview_uses_cached_result_before_build_and_renders_rich_preview():
    js = Path("panel/static/newsroom-actions.js").read_text(encoding="utf-8")
    load_start = js.index("async function loadModulePreview")
    load_end = js.index("document.addEventListener('click'", load_start)
    preview_flow = js[load_start:load_end]
    render_start = js.index("function renderModulePreview")
    renderer = js[render_start:load_start]

    cached_get = "requestJSON(`/api/command-center/module/${encodeURIComponent(moduleName)}/preview`)"
    build_post = "requestJSON(`/api/command-center/module/${encodeURIComponent(moduleName)}/preview`, {method:'POST'})"
    assert cached_get in preview_flow
    assert build_post in preview_flow
    assert preview_flow.index(cached_get) < preview_flow.index(build_post)
    assert "image_url" in renderer
    assert "available_for_publish" in renderer
    assert "generated_at" in renderer


def test_v3_snapshot_uses_current_v3_telegram_truth_over_stale_legacy_error():
    data = FakeData()
    data.files["state.json"] = {
        "newsroom_engine": "v3",
        "telegram_state": "error",
    }
    data.files["data/newsroom_v3_production_status.json"].update(
        {
            "error": "",
            "publish_failed": 0,
            "last_telegram_message_id": 1457,
            "reason": "no_safe_candidate",
        }
    )

    payload = _client(data).get("/api/newsroom/snapshot").get_json()

    assert payload["engine"] == "v3"
    assert payload["telegram_state"] == "ok"


def test_localization_failure_is_visible_and_retryable_instead_of_silent_forever():
    js = Path("panel/static/newsroom-live.js").read_text(encoding="utf-8")

    assert "خطا در آماده‌سازی" in js
    assert "retry-localization" in js
    assert "localization_failed" in js
    assert "catch (_)" not in js


def test_v4_mobile_navigation_is_fixed_safe_area_bar():
    css = Path("panel/static/newsroom-v4.css").read_text(encoding="utf-8")
    assert ".v4-mobile-nav" in css
    assert "position: fixed" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "grid-template-columns: repeat(5" in css


def test_production_wsgi_wires_live_feed_translator():
    wsgi = Path("panel/wsgi.py").read_text(encoding="utf-8")

    assert "from src.services import translate_to_fa" in wsgi
    assert 'config["LIVE_FEED_TRANSLATOR"] = translate_to_fa' in wsgi
