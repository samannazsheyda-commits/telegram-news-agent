from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.newsroom_v3.canary import run_one_shot_canary
from src.newsroom_v3.store import NewsroomV3Store


def _ready_story(store: NewsroomV3Store, story_id: str, url: str) -> None:
    store.upsert_story(
        story_id=story_id,
        source_item_id=story_id,
        source="Reuters",
        source_url=url,
        title=f"Fresh Iran story {story_id}",
        summary="Fresh verified detail.",
        published_at="2026-09-14T07:00:00+00:00",
        fetched_at="2026-09-14T07:01:00+00:00",
        media=[],
        source_priority="protected",
        fingerprint=f"fp-{story_id}",
        decision_state="ready",
        decision_reason="eligible",
    )


def _healthy_shadow(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "mode": "shadow",
                "sources_ok": 3,
                "sources_failed": 0,
                "processed": 8,
                "ready": 2,
                "telegram_writes": 0,
            }
        ),
        encoding="utf-8",
    )


def test_canary_refuses_to_publish_without_healthy_zero_write_shadow(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(store, "story-1", "https://example.com/1")
    store.close()

    status = data_dir / "newsroom_v3_shadow_status.json"
    status.write_text(json.dumps({"mode": "shadow", "processed": 5, "ready": 1, "sources_ok": 2, "telegram_writes": 1}), encoding="utf-8")
    calls = []

    result = run_one_shot_canary(
        data_dir=data_dir,
        publisher=lambda story: calls.append(story.story_id) or {"ok": True, "message_id": 99},
    )

    assert result["state"] == "shadow_not_healthy"
    assert result["telegram_writes"] == 0
    assert calls == []


def test_canary_skips_story_already_published_by_v2_and_publishes_only_one_safe_story(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(store, "story-old", "https://example.com/already-live")
    _ready_story(store, "story-safe", "https://example.com/safe")
    store.close()
    _healthy_shadow(data_dir / "newsroom_v3_shadow_status.json")

    (data_dir / "event_ledger.json").write_text(
        json.dumps(
            [
                {
                    "event_id": "v2-event",
                    "fingerprint": "old-fp",
                    "canonical_title": "Already live",
                    "first_seen": "2026-09-14T07:00:00+00:00",
                    "last_updated": "2026-09-14T07:00:00+00:00",
                    "primary_source": "Reuters",
                    "source_variants": ["https://example.com/already-live"],
                    "key_facts": [],
                    "published_message_ids": [444],
                    "status": "published",
                    "fingerprint_data": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    calls = []

    result = run_one_shot_canary(
        data_dir=data_dir,
        publisher=lambda story: calls.append(story.story_id) or {"ok": True, "message_id": 555},
    )

    assert result["state"] == "published"
    assert result["story_id"] == "story-safe"
    assert result["telegram_message_id"] == 555
    assert result["telegram_writes"] == 1
    assert calls == ["story-safe"]


def test_canary_marker_makes_the_external_attempt_strictly_one_shot(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(store, "story-1", "https://example.com/1")
    store.close()
    _healthy_shadow(data_dir / "newsroom_v3_shadow_status.json")
    calls = []

    first = run_one_shot_canary(
        data_dir=data_dir,
        publisher=lambda story: calls.append(story.story_id) or {"ok": False, "error": "network_ambiguous"},
    )
    second = run_one_shot_canary(
        data_dir=data_dir,
        publisher=lambda story: calls.append(story.story_id) or {"ok": True, "message_id": 999},
    )

    assert first["state"] == "failed"
    assert second["state"] == "already_attempted"
    assert calls == ["story-1"]
    marker = json.loads((data_dir / "newsroom_v3_canary_once.json").read_text(encoding="utf-8"))
    assert marker["story_id"] == "story-1"


def test_canary_requires_explicit_publisher_and_never_uses_shadow_cli_implicitly(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _healthy_shadow(data_dir / "newsroom_v3_shadow_status.json")
    with pytest.raises(ValueError, match="publisher"):
        run_one_shot_canary(data_dir=data_dir, publisher=None)
