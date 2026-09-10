from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from panel.app import create_app
from panel.command_center import bp as command_center_bp
from src.newsroom_models import LiveFeedRecord, RawNewsItem
from src.newsroom_v2 import _urgency_score
from src.panel_command_router import NEWSROOM_ACTIONS, _apply_module
from src.panel_live_feed import LiveFeedStore


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
            "data/panel_live_feed.json": [],
            "data/editorial_queue.json": [],
            "data/runtime_health.json": {
                "last_cycle_at": "2026-09-10T13:45:00+00:00",
                "last_publication_at": "2026-09-10T13:44:00+00:00",
                "last_error": "",
                "telegram_state": "ok",
                "sources_ok": 11,
                "sources_failed": 1,
                "items_fetched": 27,
            },
            "state.json": {},
        }

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        return None


def _client(data: FakeData):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test",
        "PANEL_PASSWORD_HASH": "x",
        "DATA_BACKEND": data,
    })
    app.register_blueprint(command_center_bp)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = True
    return client


def _record(item_id: str = "n1", source_url: str = "https://example.com/n1") -> LiveFeedRecord:
    now = datetime.now(timezone.utc).isoformat()
    return LiveFeedRecord(
        item_id=item_id,
        event_id="e1",
        source="Reuters",
        source_url=source_url,
        title="Iran missile alert",
        published_at_source=now,
        discovered_at=now,
        decision="new_event",
        decision_reason="no_matching_event",
        duplicate_of="",
        telegram_message_id=None,
        panel_status="new",
        updated_at=now,
    )


def test_dashboard_is_monitoring_room_not_newsroom():
    dashboard = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    base = Path("panel/templates/base.html").read_text(encoding="utf-8")
    combined = dashboard + base
    assert "اتاق مانیتورینگ بی‌خبر" in combined
    assert "اتاق خبر بی‌خبر" not in combined
    assert ">مانیتورینگ<" in base


def test_priority_rules_round_trip_through_settings_api():
    data = FakeData()
    client = _client(data)
    rules = ["موشک از ایران", "موشک به ایران", "انفجار", "حمله به سفارت"]
    response = client.post(
        "/api/command-center/settings",
        json={
            "freshness_hours": 2,
            "quiet_mode": False,
            "quiet_start": "00:00",
            "quiet_end": "07:00",
            "priority_rules": rules,
        },
    )
    assert response.status_code == 200
    assert response.get_json()["settings"]["priority_rules"] == rules
    assert data.files["data/newsroom_settings.json"]["priority_rules"] == rules


def test_custom_priority_rule_changes_runtime_urgency_order():
    now = datetime.now(timezone.utc).isoformat()
    custom = RawNewsItem("Test", "https://a", "1", now, now, "حمله به سفارت در منطقه", "")
    normal = RawNewsItem("Test", "https://b", "2", now, now, "نشست اقتصادی منطقه", "")
    rules = ["حمله به سفارت"]
    assert _urgency_score(custom, rules) > _urgency_score(normal, rules)


def test_health_endpoint_reads_dedicated_runtime_heartbeat():
    client = _client(FakeData())
    payload = client.get("/api/command-center/health").get_json()
    assert payload["last_cycle_at"] == "2026-09-10T13:45:00+00:00"
    assert payload["last_publication_at"] == "2026-09-10T13:44:00+00:00"
    assert payload["telegram_state"] == "ok"
    assert payload["sources_ok"] == 11
    assert payload["sources_failed"] == 1
    assert payload["items_fetched"] == 27


def test_manual_refresh_is_current_newsroom_action(tmp_path, monkeypatch):
    assert "refresh" in NEWSROOM_ACTIONS
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir()
    with patch("src.newsroom_runtime_v2.run_once", return_value={
        "items_fetched": 9,
        "panel_feed_count": 4,
        "published": 1,
        "sources_ok": 7,
        "sources_failed": 0,
    }) as runner:
        result = _apply_module({"action": "refresh", "command_id": "scan1"})
    assert result["status"] == "succeeded"
    assert "9" in result["message"]
    runner.assert_called_once()


def test_live_feed_dismissal_is_durable_across_future_upserts(tmp_path):
    store = LiveFeedStore(tmp_path / "panel_live_feed.json")
    row = _record()
    store.upsert(row)
    assert len(store.records()) == 1
    store.dismiss([row.item_id], [row.source_url])
    assert store.records() == []
    store.upsert(row)
    assert store.records() == []
    assert (tmp_path / "panel_dismissed.json").is_file()


def test_live_js_keeps_selection_across_one_second_refreshes():
    js = Path("panel/static/live.js").read_text(encoding="utf-8")
    assert "selectedNewsIds = new Set" in js
    assert "check.checked = selectedNewsIds.has(id)" in js
    assert "selectedNewsIds.add" in js
    assert "selectedNewsIds.delete" in js
    assert "setInterval(refreshLiveFeed, 1000)" in js


def test_opening_module_preview_forces_fresh_build_before_get():
    js = Path("panel/static/live.js").read_text(encoding="utf-8")
    assert "ساخت پیش‌نمایش تازه" in js
    assert "postJson(`/api/command-center/module/${name}/preview`)" in js
    assert "previewBuildOnOpen" in js


def test_settings_are_compact_and_anchored_after_live_content():
    dashboard = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    settings_js = Path("panel/static/settings.js").read_text(encoding="utf-8")
    assert 'id="agentSettingsAnchor"' in dashboard
    assert dashboard.index('id="agentSettingsAnchor"') > dashboard.index('id="liveFeed"')
    assert "agent-settings-details" in settings_js
    assert "getElementById('agentSettingsAnchor')" in settings_js


def test_secondary_pages_are_persian_first_and_do_not_expose_english_ui_labels():
    review = Path("panel/templates/review_queue.html").read_text(encoding="utf-8")
    history = Path("panel/templates/history.html").read_text(encoding="utf-8")
    sources = Path("panel/templates/source_manager.html").read_text(encoding="utf-8")
    assert "item.original_title }}" not in review
    assert "item.original_summary }}" not in review
    assert "item.status }}" not in history
    for english_ui in ("SOURCE MANAGER", "MONITORED SOURCES", ">Telegram<", ">Website / RSS<"):
        assert english_ui not in sources
