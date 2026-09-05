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


def test_merge_state_keeps_recent_published_from_concurrent_runs():
    remote_record = {
        "key": "remote-key",
        "source": "Al Jazeera English / X",
        "title": "Fitch removes Qatar negative watch while retaining AA rating",
        "summary": "",
        "link": "https://x.com/AJEnglish/status/100",
        "published": "Sat, 05 Sep 2026 12:20:00 +0000",
        "sent_at": "2026-09-05T12:23:00+00:00",
    }
    local_record = {
        "key": "local-key",
        "source": "Reuters / X",
        "title": "Iran update",
        "summary": "",
        "link": "https://x.com/Reuters/status/200",
        "published": "Sat, 05 Sep 2026 12:24:00 +0000",
        "sent_at": "2026-09-05T12:25:00+00:00",
    }

    merged = merge_state(
        {"news_seen": ["remote-key"], "recent_published_news": [remote_record]},
        {"news_seen": ["local-key"], "recent_published_news": [local_record]},
    )

    assert [record["key"] for record in merged["recent_published_news"]] == ["local-key", "remote-key"]


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
