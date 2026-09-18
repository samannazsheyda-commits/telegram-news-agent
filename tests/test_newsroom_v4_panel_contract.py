from __future__ import annotations

from pathlib import Path

from panel.app import create_app
from panel.live_api import bp as live_api_bp
from panel.newsroom_api import bp as newsroom_api_bp


class FakeData:
    def __init__(self):
        self.files = {
            "data/newsroom_settings.json": {
                "auto_publish": True,
                "emergency_lock": False,
                "daily_limit": 35,
                "special_limit": 5,
                "priority_terms": ["ایران"],
            },
            "data/newsroom_v3_production_status.json": {
                "mode": "production",
                "daily_limit": 35,
                "daily_published": 12,
                "daily_remaining": 23,
                "last_cycle_at": "2026-09-18T12:00:00+00:00",
            },
            "state.json": {"newsroom_engine": "v3"},
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/panel_live_feed.json": [
                {
                    "item_id": "story-1",
                    "news_key": "story-1",
                    "source": "Reuters",
                    "source_url": "https://example.com/story-1",
                    "title": "Breaking headline",
                    "summary": "Important details",
                    "panel_status": "new",
                    "published_at_source": "2026-09-18T12:00:00+00:00",
                    "updated_at": "2026-09-18T12:00:00+00:00",
                }
            ],
        }

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        del sha, message
        self.files[path] = value
        return {"sha": "next"}

    def mark_news_seen(self, key):
        del key


def _client(data: FakeData, translator=lambda text: f"ترجمه {text}" if text else ""):
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": data,
            "LIVE_FEED_TRANSLATOR": translator,
        }
    )
    app.register_blueprint(live_api_bp)
    app.register_blueprint(newsroom_api_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def test_machine_translation_is_network_lightweight_and_not_argos():
    source = Path("panel/live_api.py").read_text(encoding="utf-8")
    assert "offline_translation" not in source
    assert "LIVE_FEED_TRANSLATOR" in source
    assert "/api/live-feed/machine-translate" in source


def test_machine_translation_endpoint_returns_operator_preview():
    data = FakeData()
    payload = _client(data).post("/api/live-feed/machine-translate", json={"ids": ["story-1"]}).get_json()
    assert payload["ok"] is True
    assert payload["items"][0]["title"].startswith("ترجمه")
    assert payload["items"][0]["translation_mode"] == "machine"


def test_snapshot_exposes_real_daily_quota_and_limits_live_payload():
    data = FakeData()
    payload = _client(data).get("/api/newsroom/snapshot").get_json()
    assert payload["v3"]["daily_limit"] == 35
    assert payload["v3"]["daily_published"] == 12
    assert payload["v3"]["daily_remaining"] == 23
    assert payload["settings"]["daily_limit"] == 35
    assert payload["settings"]["special_limit"] == 5
    assert len(payload["live"]) <= 24


def test_panel_has_separate_machine_luna_and_publish_actions():
    js = Path("panel/static/newsroom-live.js").read_text(encoding="utf-8")
    actions = Path("panel/static/newsroom-actions.js").read_text(encoding="utf-8")
    assert "ترجمه ماشینی" in js
    assert "ترجمه و ویراستاری با لونا" in js
    assert "انتشار نسخه لونا" in js
    assert "/api/live-feed/machine-translate" in js
    assert "/luna" in actions
    assert "prepared_title" in actions


def test_panel_daily_limit_is_editable_from_dashboard():
    dashboard = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    assert 'id="dailyLimitInput"' in dashboard
    assert 'id="saveDailyLimit"' in dashboard
    assert "۳۵ خبر" in dashboard or "dailyLimit" in dashboard


def test_runtime_reads_daily_limit_from_panel_settings():
    runtime = Path("src/newsroom_hybrid_runtime.py").read_text(encoding="utf-8")
    assert 'newsroom_settings.get("daily_limit")' in runtime
    assert "daily_limit=" in runtime


def test_luna_prepare_is_distinct_from_publish():
    router = Path("src/panel_command_router.py").read_text(encoding="utf-8")
    assert '"v3_prepare"' in router
    assert '"v3_publish_prepared"' in router
    assert "_apply_v3_prepare" in router


def test_v4_css_disables_heavy_mobile_blur_and_animation():
    base = Path("panel/templates/base.html").read_text(encoding="utf-8")
    css = Path("panel/static/newsroom-v4.css").read_text(encoding="utf-8")
    assert "newsroom-v4.css" in base
    assert "backdrop-filter: none" in css
    assert "animation: none" in css
