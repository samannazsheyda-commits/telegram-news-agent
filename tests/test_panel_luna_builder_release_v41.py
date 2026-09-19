from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from panel.luna_tool_runtime import execute_luna_tool


class MemoryData:
    def __init__(self):
        self.mapping = {
            "data/panel_pending_actions.json": [
                {
                    "id": "builder-action",
                    "status": "completed",
                    "result": {"pull_request": {"number": 123}},
                }
            ]
        }

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), None


class Toolbox:
    def __init__(self, data):
        self.data = data


class FakeBuilder:
    timeout = 30

    def __init__(self, *, green=True):
        self.green = green
        self.merge_calls = []

    def _request(self, method, path, **kwargs):
        if method == "GET" and path == "/pulls/123":
            return {
                "number": 123,
                "html_url": "https://github.com/example/repo/pull/123",
                "state": "open",
                "draft": False,
                "mergeable": True,
                "merged": False,
                "node_id": "PR_node",
                "head": {"sha": "head-sha"},
                "base": {"ref": "main", "sha": "base-sha"},
            }
        if method == "GET" and path.startswith("/actions/runs?"):
            conclusion = "success" if self.green else "failure"
            return {
                "workflow_runs": [
                    {"name": "Pull Request Check", "status": "completed", "conclusion": conclusion},
                    {"name": "Telegram News Agent CI", "status": "completed", "conclusion": conclusion},
                ]
            }
        if method == "PUT" and path == "/pulls/123/merge":
            self.merge_calls.append(kwargs)
            return {"merged": True, "sha": "merge-sha", "message": "merged"}
        raise AssertionError((method, path, kwargs))


def test_builder_merge_is_refused_when_ci_is_not_green():
    builder = FakeBuilder(green=False)
    with patch("panel.luna_tool_runtime.configured_builder", return_value=builder):
        result = execute_luna_tool(
            Toolbox(MemoryData()),
            "builder_prepare_merge",
            {},
        )

    assert result["ok"] is False
    assert result["error"] == "builder_ci_not_green"
    assert builder.merge_calls == []


def test_green_builder_merge_requires_confirmation_then_merges_same_head():
    builder = FakeBuilder(green=True)
    toolbox = Toolbox(MemoryData())
    with patch("panel.luna_tool_runtime.configured_builder", return_value=builder):
        proposed = execute_luna_tool(toolbox, "builder_prepare_merge", {})
        merged = execute_luna_tool(
            toolbox,
            "builder_prepare_merge",
            proposed["pending_action"]["payload"],
            confirmed=True,
        )

    assert proposed["confirmation_required"] is True
    assert proposed["pending_action"]["payload"]["expected_head_sha"] == "head-sha"
    assert merged["ok"] is True
    assert merged["merged"] is True
    assert merged["merge_sha"] == "merge-sha"
    assert merged["rollback_sha"] == "base-sha"
    assert len(builder.merge_calls) == 1
