from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from panel.app import create_app
from panel.luna_operator_api import bp as luna_operator_bp


class MemoryData:
    def __init__(self):
        self.mapping = {
            "data/panel_pending_actions.json": [],
            "data/panel_audit_log.json": [],
            "data/panel_live_feed.json": [],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/custom_sources.json": [],
            "data/source_overrides.json": {},
            "data/newsroom_v3_production_status.json": {},
            "state.json": {},
        }

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), None

    def write_json(self, path, value, sha, message):
        del sha, message
        self.mapping[path] = deepcopy(value)
        return "sha"


class FakeToolCallingClient:
    fast_model = "gpt-5"

    def __init__(self):
        self.calls = []

    def create_response(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if len(self.calls) == 1:
            return {
                "id": "resp-first",
                "output": [
                    {"id": "rs-first", "type": "reasoning", "content": []},
                    {
                        "id": "fc-first",
                        "type": "function_call",
                        "call_id": "call-first",
                        "name": "inspect_panel_state",
                        "arguments": "{}",
                    },
                ],
            }
        return {
            "id": "resp-final",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "وضعیت اتاق خبر بررسی شد."}],
                }
            ],
        }

    @staticmethod
    def function_calls(response):
        calls = []
        for item in response.get("output") or []:
            if item.get("type") == "function_call":
                calls.append(
                    {
                        "call_id": item.get("call_id", ""),
                        "name": item.get("name", ""),
                        "arguments": {},
                    }
                )
        return calls

    @staticmethod
    def output_text(response):
        for item in response.get("output") or []:
            if item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    return part.get("text", "")
        return ""


def _client():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": MemoryData(),
        }
    )
    app.register_blueprint(luna_operator_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def test_operator_replays_response_and_tool_output_without_previous_response_id():
    provider = FakeToolCallingClient()

    with patch("panel.luna_operator_api.get_luna_client", return_value=provider), patch(
        "panel.luna_operator_api.execute_luna_tool",
        return_value={"ok": True, "message": "panel state ok"},
    ):
        response = _client().post(
            "/api/panel/luna/operator-chat",
            json={"message": "وضعیت اتاق خبر را بررسی کن"},
        )

    assert response.status_code == 200
    assert response.get_json()["reply_fa"] == "وضعیت اتاق خبر بررسی شد."
    assert len(provider.calls) == 2

    second = provider.calls[1]
    assert "previous_response_id" not in second
    replay = second["input_items"]
    assert any(item.get("role") == "user" for item in replay)
    assert any(item.get("type") == "reasoning" for item in replay)
    assert any(item.get("type") == "function_call" and item.get("call_id") == "call-first" for item in replay)
    assert any(item.get("type") == "function_call_output" and item.get("call_id") == "call-first" for item in replay)
