from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from panel.app import create_app
from panel.command_center import bp as command_center_bp


class FakeData:
    def __init__(self):
        self.files = {
            "data/newsroom_settings.json": {
                "auto_publish": True,
                "emergency_lock": False,
                "quiet_mode": False,
                "quiet_start": "00:00",
                "quiet_end": "07:00",
                "freshness_hours": 3,
            },
            "data/panel_live_feed.json": [
                {
                    "id": "a",
                    "item_id": "a",
                    "news_key": "news-a",
                    "source": "Reuters",
                    "source_url": "https://example.com/a",
                    "title": "Original live title",
                    "original_title": "Original live title",
                    "summary": "Original live summary",
                    "original_summary": "Original live summary",
                    "persian_title": "تیتر فارسی زنده",
                    "persian_body": "متن فارسی زنده",
                    "published_at_source": "2026-09-09T12:00:00+00:00",
                    "panel_status": "new",
                },
                {"id": "b"},
            ],
            "data/editorial_queue.json": [{"id": "q"}],
            "data/editorial_history.json": [],
            "data/weather_preview.json": {"message": "🌤️ هوای فردا", "generated_at": "2026-09-09T12:00:00+00:00"},
            "data/air_traffic_preview.json": {"message": "✈️ ترافیک هوایی منطقه"},
            "data/tanker_preview.json": {"message": "🚢 گزارش هرمز"},
            "data/market_preview.json": {"message": "💵 بازار ایران"},
            "state.json": {"last_cycle_at": "2026-09-09T12:00:00+00:00", "last_publication_at": "2026-09-09T11:59:00+00:00"},
            "panel_results/cmd-ok.json": {"command_id": "cmd-ok", "status": "succeeded", "message": "انجام شد", "updated_at": "2026-09-09T12:00:01+00:00"},
        }
        self.commands = []

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        if path.startswith("panel_commands/"):
            self.commands.append(value)
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        return None


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    return match.group(1)


def _app(data):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "PANEL_PASSWORD_HASH": generate_password_hash("pass"),
        "DATA_BACKEND": data,
        "LIVE_FEED_TRANSLATOR": lambda text: text,
    })
    app.register_blueprint(command_center_bp)
    return app


def _login(client):
    page = client.get("/login")
    token = _csrf(page.get_data(as_text=True))
    client.post("/login", data={"password": "pass", "csrf_token": token})
    dashboard = client.get("/").get_data(as_text=True)
    meta = re.search(r'<meta name="csrf-token" content="([^"]+)"', dashboard)
    assert meta
    return meta.group(1)


def test_status_requires_authentication():
    client = _app(FakeData()).test_client()
    response = client.get("/api/command-center/status")
    assert response.status_code == 401


def test_status_reports_safe_operational_capabilities():
    data = FakeData()
    client = _app(data).test_client()
    _login(client)
    response = client.get("/api/command-center/status")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["publishing"] is True
    assert payload["live_count"] == 2
    assert payload["queue_count"] == 1
    assert payload["poll_seconds"] == 5
    for name in ("weather", "air-traffic", "tanker", "market"):
        assert payload["modules"][name]["available"] is True
    assert payload["settings"]["freshness_hours"] == 3
    assert payload["settings"]["quiet_mode"] is False
    serialized = str(payload).lower()
    assert "token" not in serialized
    assert "password" not in serialized


def test_command_result_endpoint_reports_terminal_result():
    data = FakeData(); client = _app(data).test_client(); _login(client)
    response = client.get("/api/command-center/command/cmd-ok")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "succeeded"
    assert payload["message"] == "انجام شد"


def test_command_result_endpoint_reports_queued_when_no_result_exists():
    data = FakeData(); client = _app(data).test_client(); _login(client)
    response = client.get("/api/command-center/command/unknown")
    assert response.status_code == 200
    assert response.get_json()["status"] == "queued"


def test_health_uses_persisted_state_and_never_claims_fake_online():
    data = FakeData(); client = _app(data).test_client(); _login(client)
    response = client.get("/api/command-center/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["last_cycle_at"] == "2026-09-09T12:00:00+00:00"
    assert payload["last_publication_at"] == "2026-09-09T11:59:00+00:00"
    assert payload["agent_state"] in {"active", "stale", "unknown"}
    assert payload["telegram_state"] in {"ok", "error", "unknown"}


def test_module_preview_endpoint_reads_latest_persisted_preview_without_publishing():
    data = FakeData(); client = _app(data).test_client(); _login(client)
    expected = {
        "weather": "🌤️ هوای فردا",
        "air-traffic": "✈️ ترافیک هوایی منطقه",
        "tanker": "🚢 گزارش هرمز",
        "market": "💵 بازار ایران",
    }
    for module, message in expected.items():
        response = client.get(f"/api/command-center/module/{module}/preview")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["message"] == message
        assert data.commands == []


def test_panic_stop_and_resume_are_persisted():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)
    stopped = client.post("/api/command-center/publishing", json={"enabled": False}, headers={"X-CSRFToken": csrf})
    assert stopped.status_code == 200
    assert stopped.get_json()["publishing"] is False
    assert data.files["data/newsroom_settings.json"]["emergency_lock"] is True
    resumed = client.post("/api/command-center/publishing", json={"enabled": True}, headers={"X-CSRFToken": csrf})
    assert resumed.status_code == 200
    assert resumed.get_json()["publishing"] is True
    assert data.files["data/newsroom_settings.json"]["emergency_lock"] is False


def test_live_settings_update_runtime_supported_fields():
    data = FakeData(); client = _app(data).test_client(); csrf = _login(client)
    response = client.post("/api/command-center/settings", json={"freshness_hours": 1, "quiet_mode": True, "quiet_start": "01:30", "quiet_end": "06:15"}, headers={"X-CSRFToken": csrf})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["settings"]["freshness_hours"] == 1
    assert payload["settings"]["quiet_mode"] is True
    saved = data.files["data/newsroom_settings.json"]
    assert saved["freshness_hours"] == 1
    assert saved["quiet_start"] == "01:30"
    assert saved["quiet_end"] == "06:15"


def test_live_settings_are_validated_and_clamped():
    data = FakeData(); client = _app(data).test_client(); csrf = _login(client)
    response = client.post("/api/command-center/settings", json={"freshness_hours": 99, "quiet_mode": True, "quiet_start": "88:10", "quiet_end": "bad"}, headers={"X-CSRFToken": csrf})
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_settings"


def test_supported_modules_enqueue_real_commands():
    data = FakeData(); client = _app(data).test_client(); csrf = _login(client)
    expected = {"scan": "refresh", "weather": "weather_now", "air-traffic": "air_traffic_now", "tanker": "tanker_now", "market": "market_now"}
    for module_name, action in expected.items():
        response = client.post(f"/api/command-center/module/{module_name}", headers={"X-CSRFToken": csrf})
        assert response.status_code == 202
        assert data.commands[-1]["action"] == action


def test_bulk_clear_enqueues_selected_scope_and_ids():
    data = FakeData(); client = _app(data).test_client(); csrf = _login(client)
    response = client.post("/api/command-center/clear", json={"scope": "live", "ids": ["a", "b"]}, headers={"X-CSRFToken": csrf})
    assert response.status_code == 202
    assert data.commands[-1]["action"] == "clear"
    assert data.commands[-1]["scope"] == "live"
    assert data.commands[-1]["ids"] == ["a", "b"]


def test_any_live_item_can_be_promoted_to_review_for_editing():
    data = FakeData(); client = _app(data).test_client(); csrf = _login(client)
    response = client.post("/api/command-center/live/a/review", headers={"X-CSRFToken": csrf})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["review_url"] == "/review/a"
    queued = next(row for row in data.files["data/editorial_queue.json"] if row.get("id") == "a")
    assert queued["status"] == "pending"
    assert queued["persian_title"] == "تیتر فارسی زنده"
    assert queued["persian_body"] == "متن فارسی زنده"
    assert queued["original_title"] == "Original live title"
    assert queued["original_summary"] == "Original live summary"
    assert queued["source"] == "Reuters"
    assert queued["source_url"] == "https://example.com/a"


def test_unknown_module_is_404():
    data = FakeData(); client = _app(data).test_client(); csrf = _login(client)
    unknown = client.post("/api/command-center/module/nope", headers={"X-CSRFToken": csrf})
    assert unknown.status_code == 404
