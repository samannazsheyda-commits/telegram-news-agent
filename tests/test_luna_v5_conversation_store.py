from __future__ import annotations

import pytest

from panel.app_v5 import create_app
from panel.luna_conversation import LunaConversationStore, LunaSqliteConversationStore
from panel.luna_operator_api import bp as luna_operator_bp
from src.newsroom_v5_store import NewsroomV5Store
from tests.test_luna_v5_operator import MemoryData, ScriptedClient


@pytest.fixture(params=["sqlite", "file"])
def conversation(request, tmp_path):
    if request.param == "sqlite":
        return LunaSqliteConversationStore(NewsroomV5Store(tmp_path / "v5.db"), max_messages=4)
    return LunaConversationStore(tmp_path / "conversation.json", max_messages=4)


def test_messages_are_bounded_and_ordered(conversation):
    for index in range(6):
        conversation.append("c1", "user" if index % 2 == 0 else "assistant", f"m{index}")
    assert [row["content"] for row in conversation.recent("c1")] == ["m2", "m3", "m4", "m5"]


def test_context_preserves_story_source_pending_and_builder_pr(conversation):
    conversation.update_context("c1", last_story_id="st1", last_source_id="src", pending_action_id="a1", last_builder_pr=7)
    conversation.append("c1", "user", "hello")
    assert conversation.get_context("c1") == {
        "last_story_id": "st1", "last_source_id": "src", "pending_action_id": "a1", "last_builder_pr": 7,
    }
    conversation.update_context("c1", pending_action_id="")
    assert "pending_action_id" not in conversation.get_context("c1")
    assert conversation.get_context("c1")["last_story_id"] == "st1"


def test_context_never_counts_as_a_message(conversation):
    conversation.update_context("c1", last_story_id="st1")
    assert conversation.recent("c1") == []


def test_unknown_context_keys_are_dropped(conversation):
    conversation.update_context("c1", last_story_id="st1", secret="x")
    assert conversation.get_context("c1") == {"last_story_id": "st1"}


def test_conversations_are_strictly_separated(conversation):
    conversation.append("c1", "user", "only-one")
    conversation.update_context("c1", last_story_id="st1")
    assert conversation.recent("c2") == []
    assert conversation.get_context("c2") == {}


def _client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


@pytest.fixture
def app(tmp_path, monkeypatch):
    store = NewsroomV5Store(tmp_path / "v5.db")
    app = create_app({
        "TESTING": True, "WTF_CSRF_ENABLED": False, "SECRET_KEY": "t", "PANEL_PASSWORD_HASH": "x",
        "DATA_BACKEND": MemoryData(), "NEWSROOM_V5_STORE": store,
    })
    app.register_blueprint(luna_operator_bp)
    monkeypatch.setenv("LUNA_CONVERSATION_PATH", str(tmp_path / "must-not-be-used.json"))
    return app


def test_v5_runtime_persists_conversation_in_sqlite_across_requests(app, tmp_path, monkeypatch):
    fake = ScriptedClient([{"text": "سلام! در خدمتم."}, {"text": "گفتی سلام."}])
    monkeypatch.setattr("panel.luna_operator_api.get_luna_client", lambda: fake)
    client = _client(app)
    client.post("/api/panel/luna/operator-chat", json={"message": "سلام"})
    client.post("/api/panel/luna/operator-chat", json={"message": "چی گفتم؟"})
    second_input = fake.requests[1]["input_items"]
    assert [item["content"][0]["text"] for item in second_input] == ["سلام", "سلام! در خدمتم.", "چی گفتم؟"]
    history = client.get("/api/panel/luna/operator-history").get_json()["messages"]
    assert [row["content"] for row in history] == ["سلام", "سلام! در خدمتم.", "چی گفتم؟", "گفتی سلام."]
    rows = app.extensions["newsroom_v5_store"].conn.execute(
        "SELECT COUNT(*) FROM luna_conversations WHERE role IN ('user','assistant')").fetchone()[0]
    assert rows == 4
    assert not (tmp_path / "must-not-be-used.json").exists()


def test_two_sessions_never_see_each_other(app, monkeypatch):
    fake = ScriptedClient([{"text": "a"}, {"text": "b"}])
    monkeypatch.setattr("panel.luna_operator_api.get_luna_client", lambda: fake)
    first, second = _client(app), _client(app)
    first.post("/api/panel/luna/operator-chat", json={"message": "راز اول"})
    second.post("/api/panel/luna/operator-chat", json={"message": "پیام دوم"})
    assert [item["content"][0]["text"] for item in fake.requests[1]["input_items"]] == ["پیام دوم"]
    assert [row["content"] for row in second.get("/api/panel/luna/operator-history").get_json()["messages"]] == ["پیام دوم", "b"]
