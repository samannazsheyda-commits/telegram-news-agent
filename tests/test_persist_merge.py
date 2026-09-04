from __future__ import annotations

import json

from src.persist_merge import merge_snapshot, merge_state


def test_merge_state_keeps_manual_and_runtime_seen_keys():
    merged = merge_state(
        {"news_seen": ["manual", "shared"], "remote_only": 1},
        {"news_seen": ["auto", "shared"], "market_last_sent_at": "now"},
    )
    assert merged["news_seen"][:3] == ["auto", "shared", "manual"]
    assert merged["remote_only"] == 1
    assert merged["market_last_sent_at"] == "now"


def test_merge_snapshot_preserves_remote_and_local_editorial_records(tmp_path):
    repo = tmp_path / "repo"
    snap = tmp_path / "snap"
    (repo / "data").mkdir(parents=True)
    (snap / "data").mkdir(parents=True)
    (repo / "state.json").write_text(json.dumps({"news_seen": ["remote"]}), encoding="utf-8")
    (snap / "state.json").write_text(json.dumps({"news_seen": ["local"]}), encoding="utf-8")
    (repo / "data/editorial_queue.json").write_text(json.dumps([{"id": "r", "updated_at": "1"}]), encoding="utf-8")
    (snap / "data/editorial_queue.json").write_text(json.dumps([{"id": "l", "updated_at": "2"}]), encoding="utf-8")
    (repo / "data/editorial_history.json").write_text("[]", encoding="utf-8")
    (snap / "data/editorial_history.json").write_text("[]", encoding="utf-8")

    merge_snapshot(snap, repo)

    queue = json.loads((repo / "data/editorial_queue.json").read_text(encoding="utf-8"))
    state = json.loads((repo / "state.json").read_text(encoding="utf-8"))
    assert {x["id"] for x in queue} == {"r", "l"}
    assert state["news_seen"] == ["local", "remote"]
