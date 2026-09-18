from __future__ import annotations

from copy import deepcopy

from panel.app import create_app
from panel.luna_assistant import bp as luna_assistant_bp
from panel.v4 import bp as panel_v4_bp


class MemoryData:
    def __init__(self, mapping: dict[str, object]):
        self.mapping = deepcopy(mapping)

    def read_json(self, path: str, default):
        return deepcopy(self.mapping.get(path, default)), None

    def write_json(self, path: str, value, sha, message: str):
        self.mapping[path] = deepcopy(value)
        return "memory-sha"


def _client():
    data = MemoryData(
        {
            "data/newsroom_settings.json": {"daily_limit": 35, "special_daily_limit": 5, "auto_publish": True},
            "data/newsroom_v3_production_status.json": {
                "daily_limit": 35,
                "daily_published": 12,
                "daily_remaining": 23,
                "ready": 2,
                "waiting": 42,
                "sources_failed": 3,
                "publish_failed": 0,
                "reason": "no_safe_candidate",
            },
            "data/editorial_history.json": [
                {"id": "p1", "status": "published_auto", "persian_title": "خبر اول", "updated_at": "2026-09-18T12:00:00Z"},
                {"id": "p2", "status": "published_manual", "persian_title": "خبر دوم", "updated_at": "2026-09-18T11:00:00Z"},
            ],
            "data/panel_audit_log.json": [],
            "data/panel_pending_actions.json": [],
            "state.json": {"telegram_state": "ok"},
        }
    )
    app = create_app({"TESTING": True, "SECRET_KEY": "x", "WTF_CSRF_ENABLED": False, "DATA_BACKEND": data})
    app.register_blueprint(panel_v4_bp)
    app.register_blueprint(luna_assistant_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client, data


def test_assistant_explains_low_publish_count_from_real_panel_state():
    client, _ = _client()
    response = client.post("/api/panel/luna/assistant", json={"message": "چرا امروز خبر کم منتشر شده؟"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert "12" in payload["reply_fa"]
    assert "35" in payload["reply_fa"]
    assert "42" in payload["reply_fa"]
    assert "no_safe_candidate" in payload["reply_fa"]


def test_assistant_does_not_claim_quota_changed_until_v3_runtime_bridge_exists():
    client, data = _client()
    before = deepcopy(data.mapping["data/newsroom_settings.json"])
    response = client.post("/api/panel/luna/assistant", json={"message": "سهمیه امروز رو از 35 بکن 40"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["confirmation_required"] is False
    assert payload["action"] == "quota_runtime_bridge_required"
    assert "V3" in payload["reply_fa"]
    assert "env" in payload["reply_fa"]
    assert "35" in payload["reply_fa"]
    assert data.mapping["data/newsroom_settings.json"] == before


def test_assistant_lists_recent_published_news():
    client, _ = _client()
    response = client.post("/api/panel/luna/assistant", json={"message": "آخرین 20 خبر منتشرشده رو نشون بده"})
    payload = response.get_json()

    assert response.status_code == 200
    assert "خبر اول" in payload["reply_fa"]
    assert "خبر دوم" in payload["reply_fa"]
    assert payload["action"] == "list_recent_published"


def test_unknown_assistant_command_is_safe_and_non_mutating():
    client, data = _client()
    before = deepcopy(data.mapping["data/newsroom_settings.json"])
    response = client.post("/api/panel/luna/assistant", json={"message": "یک کار عجیب انجام بده"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["action"] == "help"
    assert data.mapping["data/newsroom_settings.json"] == before
