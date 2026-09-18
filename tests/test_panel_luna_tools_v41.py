from __future__ import annotations

from copy import deepcopy

from panel.luna_tools import LunaToolbox, tool_schemas


class MemoryData:
    def __init__(self):
        self.mapping = {
            "data/panel_live_feed.json": [
                {
                    "id": "story-1",
                    "source": "Reuters",
                    "source_url": "https://example.com/iran-1",
                    "original_title": "Iran announces new measure",
                    "original_summary": "Officials announced a measure.",
                    "panel_status": "new",
                }
            ],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/custom_sources.json": [
                {"id": "src-1", "kind": "telegram", "name": "رسالت", "channel": "resalat", "active": True}
            ],
            "data/source_overrides.json": {},
            "data/newsroom_v3_production_status.json": {"daily_published": 5, "daily_limit": 25, "ready": 3, "waiting": 2},
            "state.json": {"telegram_state": "ok"},
        }

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), None

    def write_json(self, path, value, sha, message):
        self.mapping[path] = deepcopy(value)
        return "sha"


def test_tool_schema_exposes_newsroom_actions_without_shell():
    schemas = tool_schemas()
    names = {item["name"] for item in schemas}

    assert {"search_stories", "get_story", "reject_and_block_story", "list_sources", "add_source", "disable_source", "delete_source"} <= names
    combined = repr(schemas).lower()
    assert "shell" not in combined
    assert "python" not in combined


def test_search_story_and_source_listing_are_read_only():
    data = MemoryData()
    toolbox = LunaToolbox(data, block_path="/tmp/test-luna-operator-blocks.json")

    stories = toolbox.execute("search_stories", {"query": "Iran"})
    sources = toolbox.execute("list_sources", {"active": True})

    assert stories["ok"] is True
    assert stories["stories"][0]["id"] == "story-1"
    assert any(row["name"] == "رسالت" for row in sources["sources"])


def test_destructive_source_action_requires_confirmation():
    toolbox = LunaToolbox(MemoryData(), block_path="/tmp/test-luna-operator-blocks.json")

    result = toolbox.execute("disable_source", {"source_id": "src-1"})

    assert result["confirmation_required"] is True
    assert result["pending_action"]["action"] == "disable_source"


def test_confirmed_source_disable_changes_real_source_state():
    data = MemoryData()
    toolbox = LunaToolbox(data, block_path="/tmp/test-luna-operator-blocks.json")

    result = toolbox.execute("disable_source", {"source_id": "src-1"}, confirmed=True)

    assert result["ok"] is True
    assert data.mapping["data/custom_sources.json"][0]["active"] is False


def test_ambiguous_source_name_does_not_mutate():
    data = MemoryData()
    data.mapping["data/custom_sources.json"].append(
        {"id": "src-2", "kind": "x", "name": "رسالت", "handle": "@resalat2", "active": True}
    )
    toolbox = LunaToolbox(data, block_path="/tmp/test-luna-operator-blocks.json")

    result = toolbox.execute("disable_source", {"query": "رسالت"})

    assert result["ok"] is False
    assert result["error"] == "ambiguous_source"
    assert all(row["active"] is True for row in data.mapping["data/custom_sources.json"])
