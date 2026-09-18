from panel.luna_conversation import LunaConversationStore


def test_conversation_store_keeps_only_bounded_recent_turns(tmp_path):
    store = LunaConversationStore(tmp_path / "conversations.json", max_messages=6)
    for index in range(10):
        store.append("session-a", "user" if index % 2 == 0 else "assistant", f"message-{index}")

    rows = store.recent("session-a")

    assert len(rows) == 6
    assert rows[0]["content"] == "message-4"
    assert rows[-1]["content"] == "message-9"


def test_conversation_store_is_separated_by_session(tmp_path):
    store = LunaConversationStore(tmp_path / "conversations.json")
    store.append("a", "user", "الف")
    store.append("b", "user", "ب")

    assert [row["content"] for row in store.recent("a")] == ["الف"]
    assert [row["content"] for row in store.recent("b")] == ["ب"]
