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
            "data/panel_live_feed.json": [{"id": "a"}, {"id": "b"}],
            "data/editorial_queue.json": [{"id": "q"}],
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
    assert payload["modules"]["weather"]["available"] is True
    assert payload["modules"]["air-traffic"]["available"] is True
    assert payload["modules"]["tanker"]["available"] is False
    assert payload["modules"]["market"]["available"] is False
    assert payload["settings"]["freshness_hours"] == 3
    assert payload["settings"]["quiet_mode"] is False
    serialized = str(payload).lower()
    assert "token" not in serialized
    assert "password" not in serialized


def test_panic_stop_and_resume_are_persisted():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)
    stopped = client.post(
        "/api/command-center/publishing",
        json={"enabled": False},
        headers={"X-CSRFToken": csrf},
    )
    assert stopped.status_code == 200
    assert stopped.get_json()["publishing"] is False
    assert data.files["data/newsroom_settings.json"]["emergency_lock"] is True

    resumed = client.post(
        "/api/command-center/publishing",
        json={"enabled": True},
        headers={"X-CSRFToken": csrf},
    )
    assert resumed.status_code == 200
    assert resumed.get_json()["publishing"] is True
    assert data.files["data/newsroom_settings.json"]["emergency_lock"] is False


def test_live_settings_update_runtime_supported_fields():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)
    response = client.post(
        "/api/command-center/settings",
        json={
            "freshness_hours": 1,
            "quiet_mode": True,
            "quiet_start": "01:30",
            "quiet_end": "06:15",
        },
        headers={"X-CSRFToken": csrf},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["settings"]["freshness_hours"] == 1
    assert payload["settings"]["quiet_mode"] is True
    saved = data.files["data/newsroom_settings.json"]
    assert saved["freshness_hours"] == 1
    assert saved["quiet_start"] == "01:30"
    assert saved["quiet_end"] == "06:15"


def test_live_settings_are_validated_and_clamped():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)
    response = client.post(
        "/api/command-center/settings",
        json={"freshness_hours": 99, "quiet_mode": True, "quiet_start": "88:10", "quiet_end": "bad"},
        headers={"X-CSRFToken": csrf},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_settings"


def test_supported_modules_enqueue_real_commands():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)
    expected = {"scan": "refresh", "weather": "weather_now", "air-traffic": "air_traffic_now"}
    for module_name, action in expected.items():
        response = client.post(
            f"/api/command-center/module/{module_name}",
            headers={"X-CSRFToken": csrf},
        )
        assert response.status_code == 202
        assert data.commands[-1]["action"] == action


def test_known_unwired_modules_are_explicitly_unavailable():
    data = FakeData()
    client = _app(data).test_client()
    csrf = _login(client)
    for module_name in ("tanker", "market"):
        response = client.post(
            f"/api/command-center/module/{module_name}",
            headers={"X-CSRFToken": csrf},
        )
        assert response.status_code == 409
        assert response.get_json()["error"] == "module_unavailable"
    unknown = client.post(
        "/api/command-center/module/nope",
        headers={"X-CSRFToken": csrf},
    )
    assert unknown.status_code == 404
