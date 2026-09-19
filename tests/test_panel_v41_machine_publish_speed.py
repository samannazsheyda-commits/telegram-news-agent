from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from panel.app import create_app
from panel.luna_operator_api import bp as luna_operator_bp
from panel.luna_tool_runtime import execute_luna_tool
from panel.luna_tools import LunaToolbox
from panel.luna_translation_api import bp as luna_translation_bp
from panel.openai_luna import OpenAILunaClient


class MemoryData:
    def __init__(self):
        self.mapping = {
            "data/panel_live_feed.json": [
                {
                    "id": "story-1",
                    "item_id": "story-1",
                    "news_key": "story-1",
                    "source": "Bloomberg",
                    "source_url": "https://example.com/story-1",
                    "original_title": "Pentagon investigators found flawed intelligence",
                    "original_summary": "The investigation describes failures before the strike.",
                    "persian_title": "بازرسان پنتاگون از نقص اطلاعات پیش از حمله خبر دادند",
                    "persian_body": "این تحقیقات به چند نقص اطلاعاتی پیش از حمله اشاره می‌کند.",
                    "panel_status": "new",
                    "updated_at": "2026-09-19T07:00:00+00:00",
                }
            ],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/custom_sources.json": [],
            "data/source_overrides.json": {},
            "data/panel_pending_actions.json": [],
            "data/panel_audit_log.json": [],
            "state.json": {"daily_published": 0, "daily_limit": 35},
        }

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), None

    def write_json(self, path, value, sha, message):
        del sha, message
        self.mapping[path] = deepcopy(value)
        return "memory-sha"


def _base_app(data: MemoryData):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "WTF_CSRF_ENABLED": False,
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": data,
        }
    )


def _login(client):
    with client.session_transaction() as session:
        session["admin"] = True


def test_dashboard_shows_machine_persian_instead_of_english_and_offers_publish():
    app = _base_app(MemoryData())
    client = app.test_client()
    _login(client)

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "بازرسان پنتاگون از نقص اطلاعات پیش از حمله خبر دادند" in html
    assert "این تحقیقات به چند نقص اطلاعاتی پیش از حمله اشاره می‌کند." in html
    assert "Pentagon investigators found flawed intelligence" not in html
    assert "تأیید و انتشار با Luna" in html


def test_publish_endpoint_accepts_the_visible_machine_persian_copy():
    data = MemoryData()
    app = _base_app(data)
    app.register_blueprint(luna_translation_bp)
    client = app.test_client()
    _login(client)

    with patch("panel.luna_translation_api._enqueue", return_value="cmd-1") as enqueue:
        response = client.post("/api/panel/luna/publish-final/story-1")

    payload = response.get_json()
    assert response.status_code == 202
    assert payload["ok"] is True
    assert payload["command_id"] == "cmd-1"
    kwargs = enqueue.call_args.kwargs
    assert kwargs["title"] == "بازرسان پنتاگون از نقص اطلاعات پیش از حمله خبر دادند"
    assert kwargs["body"] == "این تحقیقات به چند نقص اطلاعاتی پیش از حمله اشاره می‌کند."


class FastFakeClient:
    fast_model = "gpt-5"

    def __init__(self):
        self.calls = []

    def create_response(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "resp-1", "output": []}

    @staticmethod
    def function_calls(response):
        del response
        return []

    @staticmethod
    def output_text(response):
        del response
        return "سلام، آماده‌ام."


def test_luna_exposes_publish_story_tool_and_requires_confirmation(tmp_path, monkeypatch):
    data = MemoryData()
    app = _base_app(data)
    app.register_blueprint(luna_operator_bp)
    client = app.test_client()
    _login(client)
    monkeypatch.setenv("LUNA_CONVERSATION_PATH", str(tmp_path / "luna-publish-conversation.json"))
    provider = FastFakeClient()

    with patch("panel.luna_operator_api.get_luna_client", return_value=provider):
        response = client.post("/api/panel/luna/operator-chat", json={"message": "همین خبر را منتشر کن"})

    assert response.status_code == 200
    names = {item["name"] for item in provider.calls[0]["tools"]}
    assert "publish_story" in names

    result = execute_luna_tool(
        LunaToolbox(data, block_path="/tmp/test-luna-publish-blocks.json"),
        "publish_story",
        {"story_id": "story-1"},
    )
    assert result["ok"] is True
    assert result["confirmation_required"] is True
    assert result["pending_action"]["action"] == "publish_story"
    assert "بازرسان پنتاگون" in result["pending_action"]["summary_fa"]


def test_confirmed_luna_publish_queues_exact_visible_copy():
    data = MemoryData()
    toolbox = LunaToolbox(data, block_path="/tmp/test-luna-publish-blocks.json")

    with patch("panel.luna_tool_runtime._enqueue", return_value="cmd-chat-1", create=True) as enqueue:
        result = execute_luna_tool(
            toolbox,
            "publish_story",
            {"story_id": "story-1"},
            confirmed=True,
        )

    assert result["ok"] is True
    assert result["command_id"] == "cmd-chat-1"
    kwargs = enqueue.call_args.kwargs
    assert kwargs["title"] == "بازرسان پنتاگون از نقص اطلاعات پیش از حمله خبر دادند"
    assert kwargs["body"] == "این تحقیقات به چند نقص اطلاعاتی پیش از حمله اشاره می‌کند."


class FakeHTTPResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"id": "resp-1", "output": [], "usage": {}}


def test_provider_uses_low_reasoning_for_tool_driven_routine_operator_calls():
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return FakeHTTPResponse()

    client = OpenAILunaClient(api_key="test", fast_model="gpt-5", base_url="https://example.test")
    with patch("panel.openai_luna.requests.post", side_effect=fake_post):
        client.create_response(
            input_items=[{"role": "user", "content": [{"type": "input_text", "text": "سلام"}]}],
            tools=[],
            model=client.fast_model,
        )

    assert captured["json"]["reasoning"] == {"effort": "low"}
