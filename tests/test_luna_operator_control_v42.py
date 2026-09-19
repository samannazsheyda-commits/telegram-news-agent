from __future__ import annotations

from copy import deepcopy

from panel.app import create_app
from panel.luna_operator_api import bp as luna_operator_bp
from panel.luna_tools import tool_schemas


class MemoryData:
    def __init__(self):
        self.mapping = {
            "data/panel_pending_actions.json": [],
            "data/panel_audit_log.json": [],
            "data/panel_live_feed.json": [],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/custom_sources.json": [
                {
                    "id": "src-clash",
                    "kind": "x",
                    "name": "ClashReports",
                    "handle": "ClashReports",
                    "active": True,
                }
            ],
            "data/source_overrides.json": {},
            "data/panel_settings.json": {"newsroom_alarm_enabled": True},
            "state.json": {},
        }

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), "sha"

    def write_json(self, path, value, sha, message):
        del sha, message
        self.mapping[path] = deepcopy(value)
        return {"sha": "next"}


class FakeLunaClient:
    fast_model = "gpt-5"

    def __init__(self):
        self.calls = 0

    def create_response(self, **kwargs):
        del kwargs
        self.calls += 1
        if self.calls == 1:
            return {"kind": "tool", "output": []}
        return {"kind": "done", "output": [], "text": ""}

    def function_calls(self, response):
        if response.get("kind") == "tool":
            return [
                {
                    "name": "rename_source",
                    "arguments": {"query": "ClashReports", "display_name": "کلش ریپورتز"},
                    "call_id": "call-1",
                }
            ]
        return []

    def output_text(self, response):
        return str(response.get("text") or "")


def test_model_tool_schemas_come_from_registry_and_include_source_rename():
    names = {row["name"] for row in tool_schemas()}
    assert "rename_source" in names
    assert "set_source_review_only" in names
    assert "set_newsroom_alarm" in names
    assert "builder_prepare" in names


def test_natural_clashreports_request_returns_one_specific_frozen_confirmation(monkeypatch, tmp_path):
    data = MemoryData()
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": data,
        }
    )
    app.register_blueprint(luna_operator_bp)
    fake = FakeLunaClient()
    monkeypatch.setattr("panel.luna_operator_api.get_luna_client", lambda: fake)
    monkeypatch.setenv("LUNA_CONVERSATION_PATH", str(tmp_path / "conversation.json"))

    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True

    response = client.post(
        "/api/panel/luna/operator-chat",
        json={"message": "لونا کلش ریپورتز رو فارسی بنویس و اصلاح کن"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["confirmation_required"] is True
    assert payload["summary_fa"] == "نام نمایشی ClashReports به «کلش ریپورتز» تغییر کند؟"
    assert payload["reply_fa"] == payload["summary_fa"]
    pending = data.mapping["data/panel_pending_actions.json"]
    assert len(pending) == 1
    assert pending[0]["capability"] == "rename_source"
    assert pending[0]["payload"] == {"source_id": "src-clash", "display_name": "کلش ریپورتز"}
    assert data.mapping["data/custom_sources.json"][0]["name"] == "ClashReports"

    confirmed = client.post(f"/api/panel/luna/operator-confirm/{payload['action_id']}")
    assert confirmed.status_code == 200
    assert confirmed.get_json()["ok"] is True
    assert data.mapping["data/custom_sources.json"][0]["name"] == "کلش ریپورتز"
