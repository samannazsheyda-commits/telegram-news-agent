from __future__ import annotations

from copy import deepcopy

from panel.luna_proposals import ProposalStore, proposal_fingerprint


class MemoryData:
    def __init__(self, mapping: dict | None = None):
        self.mapping = deepcopy(mapping or {"data/panel_pending_actions.json": []})

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
