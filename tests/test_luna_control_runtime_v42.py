from __future__ import annotations

from copy import deepcopy

from panel.luna_capabilities import build_capability_registry
from panel.luna_context import LunaContextResolver
from panel.luna_control_runtime import LunaControlRuntime
from panel.luna_proposals import ProposalStore
from panel.luna_tools import LunaToolbox


class MemoryData:
    def __init__(self):
        self.mapping = {
            "data/panel_pending_actions.json": [],
            "data/panel_audit_log.json": [],
            "data/panel_live_feed.json": [
                {
                    "id": "story-1",
                    "item_id": "story-1",
                    "source": "Reuters",
                    "source_url": "https://example.com/story-1",
                    "original_title": "Original title",
                    "persian_title": "تیتر ماشینی",
                    "persian_body": "متن ماشینی",
                    "panel_status": "new",
                }
            ],
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


def _runtime(data=None, enqueue=None):
    data = data or MemoryData()
    toolbox = LunaToolbox(data)
    return LunaControlRuntime(
        registry=build_capability_registry(),
        toolbox=toolbox,
        resolver=LunaContextResolver(toolbox),
        proposals=ProposalStore(data),
        enqueue=enqueue or (lambda command, **kwargs: "cmd-1"),
    )


def test_read_capability_executes_without_confirmation():
    result = _runtime().invoke("inspect_panel_state", {}, {})
    assert result["ok"] is True
    assert result.get("confirmation_required") is not True


def test_rename_source_requires_specific_confirmation_and_changes_nothing_before_confirm():
    data = MemoryData()
    runtime = _runtime(data)

    result = runtime.invoke(
        "rename_source",
        {"query": "ClashReports", "display_name": "کلش ریپورتز"},
        {},
    )

    assert result["ok"] is True
    assert result["confirmation_required"] is True
    assert result["summary_fa"] == "نام نمایشی ClashReports به «کلش ریپورتز» تغییر کند؟"
    assert data.mapping["data/custom_sources.json"][0]["name"] == "ClashReports"

    done = runtime.confirm(result["action_id"])
    assert done["ok"] is True
    assert data.mapping["data/custom_sources.json"][0]["name"] == "کلش ریپورتز"
    assert data.mapping["data/custom_sources.json"][0]["handle"] == "ClashReports"


def test_changed_source_after_proposal_fails_closed():
    data = MemoryData()
    runtime = _runtime(data)
    proposal = runtime.invoke(
        "rename_source",
        {"source_id": "src-clash", "display_name": "کلش ریپورتز"},
        {},
    )
    data.mapping["data/custom_sources.json"][0]["name"] = "Changed Elsewhere"

    result = runtime.confirm(proposal["action_id"])

    assert result["ok"] is False
    assert result["error"] == "target_changed"
    assert data.mapping["data/custom_sources.json"][0]["name"] == "Changed Elsewhere"


def test_publish_proposal_freezes_machine_copy_mode_and_queues_only_after_confirm():
    captured = {}

    def enqueue(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return "cmd-publish"

    runtime = _runtime(enqueue=enqueue)
    proposal = runtime.invoke(
        "publish_story",
        {"story_id": "story-1", "copy_mode": "machine"},
        {},
    )

    assert proposal["confirmation_required"] is True
    assert captured == {}
    saved = runtime.proposals.get_pending(proposal["action_id"])
    assert saved["payload"]["story_id"] == "story-1"
    assert saved["payload"]["copy_mode"] == "machine"

    result = runtime.confirm(proposal["action_id"])
    assert result["ok"] is True
    assert captured["command"] == "v3_publish"
    assert captured["title"] == "تیتر ماشینی"


def test_alarm_setting_requires_confirmation_and_uses_safe_settings_store():
    data = MemoryData()
    runtime = _runtime(data)

    proposal = runtime.invoke("set_newsroom_alarm", {"enabled": False}, {})

    assert proposal["confirmation_required"] is True
    assert data.mapping["data/panel_settings.json"]["newsroom_alarm_enabled"] is True
    result = runtime.confirm(proposal["action_id"])
    assert result["ok"] is True
    assert data.mapping["data/panel_settings.json"]["newsroom_alarm_enabled"] is False


def test_every_successful_mutation_is_audited():
    data = MemoryData()
    runtime = _runtime(data)
    proposal = runtime.invoke(
        "rename_source",
        {"source_id": "src-clash", "display_name": "کلش ریپورتز"},
        {},
    )
    runtime.confirm(proposal["action_id"])

    audit = data.mapping["data/panel_audit_log.json"]
    assert audit
    assert audit[0]["capability"] == "rename_source"
    assert audit[0]["target"]["id"] == "src-clash"
    assert audit[0]["status"] == "success"
