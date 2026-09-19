from __future__ import annotations

from copy import deepcopy

from panel.luna_context import LunaContextResolver
from panel.luna_conversation import LunaConversationStore
from panel.luna_proposals import ProposalStore, proposal_fingerprint
from panel.luna_tools import LunaToolbox


class MemoryData:
    def __init__(self, mapping: dict | None = None):
        base = {
            "data/panel_pending_actions.json": [],
            "data/panel_live_feed.json": [],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/custom_sources.json": [],
            "data/source_overrides.json": {},
            "state.json": {},
        }
        if mapping:
            base.update(mapping)
        self.mapping = deepcopy(base)

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), "sha"

    def write_json(self, path, value, sha, message):
        del sha, message
        self.mapping[path] = deepcopy(value)
        return {"sha": "next"}


def test_proposal_fingerprint_is_stable_for_key_order():
    assert proposal_fingerprint({"b": 2, "a": 1}) == proposal_fingerprint({"a": 1, "b": 2})


def test_proposal_freezes_exact_payload():
    data = MemoryData()
    store = ProposalStore(data, ttl_minutes=15)
    original = {"source_id": "src-1", "display_name": "کلش ریپورتز"}
    proposal = store.create(
        capability="rename_source",
        target={"type": "source", "id": "src-1"},
        payload=original,
        summary_fa="نام نمایشی تغییر کند؟",
        before={"display_name": "ClashReports"},
        after={"display_name": "کلش ریپورتز"},
        target_fingerprint="abc",
    )
    original["display_name"] = "CHANGED AFTER CREATE"

    loaded = store.get_pending(proposal["id"])
    assert loaded["payload"] == {"source_id": "src-1", "display_name": "کلش ریپورتز"}
    assert loaded["before"] == {"display_name": "ClashReports"}
    assert loaded["after"] == {"display_name": "کلش ریپورتز"}


def test_expired_proposal_cannot_execute():
    data = MemoryData()
    store = ProposalStore(data, ttl_minutes=-1)
    proposal = store.create(
        capability="disable_source",
        target={"type": "source", "id": "src-1"},
        payload={"source_id": "src-1"},
        summary_fa="غیرفعال شود؟",
        before={},
        after={},
        target_fingerprint="abc",
    )

    loaded = store.get_pending(proposal["id"])
    assert loaded["status"] == "expired"
    persisted = data.mapping["data/panel_pending_actions.json"][0]
    assert persisted["status"] == "expired"


def test_complete_marks_exact_pending_action_and_preserves_payload():
    data = MemoryData()
    store = ProposalStore(data)
    proposal = store.create(
        capability="rename_source",
        target={"type": "source", "id": "src-1"},
        payload={"source_id": "src-1", "display_name": "کلش ریپورتز"},
        summary_fa="تغییر کند؟",
        before={},
        after={},
        target_fingerprint="abc",
    )

    store.complete(proposal["id"], "success", {"ok": True, "message": "انجام شد"})

    row = data.mapping["data/panel_pending_actions.json"][0]
    assert row["status"] == "success"
    assert row["payload"]["display_name"] == "کلش ریپورتز"
    assert row["result"]["ok"] is True


def _source_data(*, ambiguous: bool = False) -> MemoryData:
    rows = [
        {
            "id": "src-clash",
            "kind": "x",
            "name": "ClashReports",
            "handle": "ClashReports",
            "active": True,
        }
    ]
    if ambiguous:
        rows.append(
            {
                "id": "src-clash-news",
                "kind": "x",
                "name": "ClashNews",
                "handle": "ClashNews",
                "active": True,
            }
        )
    return MemoryData({"data/custom_sources.json": rows})


def test_source_resolver_matches_exact_normalized_name(tmp_path):
    toolbox = LunaToolbox(_source_data(), block_path=tmp_path / "blocks.json")
    resolver = LunaContextResolver(toolbox)

    result = resolver.resolve_source({"query": "@clashreports"}, {})

    assert result["ok"] is True
    assert result["source"]["id"] == "src-clash"


def test_source_resolver_refuses_ambiguous_target(tmp_path):
    toolbox = LunaToolbox(_source_data(ambiguous=True), block_path=tmp_path / "blocks.json")
    resolver = LunaContextResolver(toolbox)

    result = resolver.resolve_source({"query": "clash"}, {})

    assert result["ok"] is False
    assert result["error"] == "ambiguous_source"
    match_ids = {row["id"] for row in result["matches"]}
    assert {"src-clash", "src-clash-news"}.issubset(match_ids)
    assert len(match_ids) >= 2


def test_story_pronoun_uses_structured_last_story_id(tmp_path):
    data = MemoryData(
        {
            "data/panel_live_feed.json": [
                {
                    "id": "story-9",
                    "source": "Reuters",
                    "source_url": "https://example.com/9",
                    "original_title": "Story nine",
                    "persian_title": "خبر شماره نه",
                    "panel_status": "new",
                }
            ]
        }
    )
    resolver = LunaContextResolver(LunaToolbox(data, block_path=tmp_path / "blocks.json"))

    result = resolver.resolve_story({}, {"last_story_id": "story-9"})

    assert result["ok"] is True
    assert result["story"]["id"] == "story-9"


def test_conversation_store_keeps_structured_context_out_of_message_history(tmp_path):
    store = LunaConversationStore(tmp_path / "conversation.json")
    store.append("c1", "user", "این خبر رو ببین")
    context = store.update_context(
        "c1",
        last_story_id="story-9",
        last_source_id="src-clash",
        ignored_field="must-not-be-stored",
    )

    assert context == {"last_story_id": "story-9", "last_source_id": "src-clash"}
    assert store.get_context("c1") == context
    history = store.recent("c1")
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert all(row.get("role") in {"user", "assistant"} for row in history)
