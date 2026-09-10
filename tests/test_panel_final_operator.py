from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from panel.app import create_app
from panel.command_center import bp as command_center_bp
from panel.live_api import bp as live_api_bp
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import _urgency_score
from src.panel_command_router import _apply_clear


class FakeData:
    def __init__(self):
        self.files = {
            "data/newsroom_settings.json": {
                "auto_publish": True,
                "emergency_lock": False,
                "quiet_mode": False,
                "quiet_start": "00:00",
                "quiet_end": "07:00",
                "freshness_hours": 2,
            },
            "data/panel_live_feed.json": [
                {
                    "item_id": "live-1",
                    "news_key": "news-1",
                    "title": "Missile launched from Iran",
                    "persian_title": "شلیک موشک از ایران",
                    "persian_body": "گزارش تازه از شلیک موشک.",
                    "final_message": "🚨 شلیک موشک از ایران",
                    "source": "Reuters",
                    "source_url": "https://example.com/1",
                    "panel_status": "new",
                    "published_at_source": "2026-09-10T21:30:00+00:00",
                    "updated_at": "2026-09-10T21:30:01+00:00",
                }
            ],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [
                {"id": "pub-1", "status": "published_auto", "final_persian_title": "خبر منتشرشده"}
            ],
            "state.json": {
                "last_cycle_at": datetime.now(timezone.utc).isoformat(),
                "last_scan_at": datetime.now(timezone.utc).isoformat(),
                "last_publication_at": "2026-09-10T20:00:00+00:00",
                "telegram_state": "ok",
                "last_sources_ok": 7,
                "last_sources_failed": 1,
                "last_items_fetched": 19,
                "last_cycle_published": 2,
            },
        }
        self.marked_seen: list[str] = []

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        self.marked_seen.append(str(key))


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    return match.group(1)


def _app(data: FakeData):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": generate_password_hash("pass"),
            "DATA_BACKEND": data,
            "LIVE_FEED_TRANSLATOR": lambda text: "ترجمه فارسی",
        }
    )
    app.register_blueprint(command_center_bp)
    app.register_blueprint(live_api_bp)
    return app


def _login(client):
    page = client.get("/login").get_data(as_text=True)
    token = _csrf(page)
    client.post("/login", data={"password": "pass", "csrf_token": token})
    dashboard = client.get("/").get_data(as_text=True)
    meta = re.search(r'<meta name="csrf-token" content="([^"]+)"', dashboard)
    assert meta
    return meta.group(1)


def test_panel_cleanup_only_removes_live_rows_and_never_publication_history():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)
    response = client.post(
        "/api/command-center/clear",
        json={"scope": "live", "ids": ["live-1"]},
        headers={"X-CSRFToken": csrf},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["telegram_untouched"] is True
    assert data.files["data/panel_live_feed.json"] == []
    assert data.files["data/editorial_history.json"] == [
        {"id": "pub-1", "status": "published_auto", "final_persian_title": "خبر منتشرشده"}
    ]

    forbidden = client.post(
        "/api/command-center/clear",
        json={"scope": "published", "ids": ["pub-1"]},
        headers={"X-CSRFToken": csrf},
    )
    assert forbidden.status_code == 400
    assert data.files["data/editorial_history.json"][0]["id"] == "pub-1"


def test_router_rejects_any_request_to_clear_published_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir()
    Path("data/editorial_queue.json").write_text("[]", encoding="utf-8")
    Path("data/editorial_history.json").write_text('[{"id":"pub-1","status":"published_auto"}]', encoding="utf-8")
    Path("data/panel_live_feed.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_clear_scope"):
        _apply_clear({"command_id": "x", "scope": "published", "ids": ["pub-1"]})
    assert "pub-1" in Path("data/editorial_history.json").read_text(encoding="utf-8")


def test_priority_rules_are_editable_persisted_and_returned():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)
    wanted = ["موشک از ایران", "موشک به ایران", "انفجار", "تنگه هرمز", "نفتکش"]
    saved = client.post(
        "/api/command-center/priorities",
        json={"priority_terms": wanted},
        headers={"X-CSRFToken": csrf},
    )
    assert saved.status_code == 200
    assert saved.get_json()["priority_terms"] == wanted
    assert data.files["data/newsroom_settings.json"]["priority_terms"] == wanted
    fetched = client.get("/api/command-center/priorities")
    assert fetched.status_code == 200
    assert fetched.get_json()["priority_terms"] == wanted


def test_custom_priority_terms_change_runtime_ordering_score():
    custom = RawNewsItem(
        source="Test",
        source_url="https://example.com/custom",
        source_item_id="custom",
        published_at="2026-09-10T21:00:00+00:00",
        fetched_at="2026-09-10T21:00:01+00:00",
        title="Naval blockade near Bab el Mandeb",
        summary="",
        media=[],
        source_priority="normal",
    )
    ordinary = RawNewsItem(
        source="Test",
        source_url="https://example.com/ordinary",
        source_item_id="ordinary",
        published_at="2026-09-10T21:00:02+00:00",
        fetched_at="2026-09-10T21:00:03+00:00",
        title="Routine diplomatic meeting",
        summary="",
        media=[],
        source_priority="normal",
    )
    assert _urgency_score(custom, ["bab el mandeb"])[0] > _urgency_score(ordinary, ["bab el mandeb"])[0]


def test_status_and_health_use_real_runtime_values(monkeypatch):
    data = FakeData()
    client = _app(data).test_client()
    _login(client)
    monkeypatch.setenv("POLL_SECONDS", "2")
    status = client.get("/api/command-center/status").get_json()
    assert status["poll_seconds"] == 2
    health = client.get("/api/command-center/health").get_json()
    assert health["sources_ok"] == 7
    assert health["sources_failed"] == 1
    assert health["items_fetched"] == 19
    assert health["published_last_cycle"] == 2
    assert health["telegram_state"] == "ok"


def test_dashboard_is_newsroom_first_and_operator_sections_are_collapsible():
    html = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    base = Path("panel/templates/base.html").read_text(encoding="utf-8")
    assert "اتاق خبر بی‌خبر" in html
    assert "اتاق فرمان" not in html + base
    assert "اولویت قرمز ۲۴/۷" in html
    assert 'id="priorityEditor"' in html
    assert 'id="clearCurrentFeed"' in html
    assert "فقط از پنل" in html
    assert 'class="ops-fold"' in html
    assert "ابزارهای عملیاتی" in html
    assert "تنظیمات و سلامت" in html
    assert html.index("ورودی زنده") < html.index("ابزارهای عملیاتی")


def test_live_client_is_fast_revisioned_stateful_and_dings():
    js = Path("panel/static/live.js").read_text(encoding="utf-8")
    assert "setInterval(refreshLiveFeed, 1000)" in js
    assert "AudioContext" in js
    assert "980" in js or "920" in js
    assert "lastFeedRevision" in js
    assert "data.revision" in js
    assert "selectedNewsIds = new Set" in js
    assert "openNewsIds = new Set" in js
    assert "حذف از پنل" in js
    assert "/api/command-center/clear" in js
    assert "telegramPreviewText" in js
    assert "final-output-details" in js
    assert "خروجی نهایی تلگرام" in js


def test_live_feed_api_has_revision_and_stays_persian_first():
    data = FakeData()
    client = _app(data).test_client()
    _login(client)
    payload = client.get("/api/live-feed").get_json()
    assert payload["revision"]
    assert payload["items"][0]["title"] == "شلیک موشک از ایران"
    assert payload["items"][0]["final_message"]
    assert payload["items"][0]["original_title"] == "Missile launched from Iran"


def test_module_preview_ui_is_inline_toggle_and_non_publishing_refresh():
    html = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    js = Path("panel/static/live.js").read_text(encoding="utf-8")
    for name in ("weather", "air-traffic", "tanker", "market"):
        assert f'data-preview-toggle="{name}"' in html
        assert f'data-preview-panel="{name}"' in html
    assert "panel.hidden = !opening" in js or "preview.hidden" in js
    assert "/preview" in js
    assert "پیش‌نمایش" in html


def test_no_telegram_delete_api_or_method_is_present_in_panel_code():
    combined = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ("panel/command_center.py", "panel/static/live.js", "src/panel_command_router.py")
    ).lower()
    assert "deletmessage" not in combined
    assert "deletemessage" not in combined
    assert "/bot{token}/deletemessage" not in combined
