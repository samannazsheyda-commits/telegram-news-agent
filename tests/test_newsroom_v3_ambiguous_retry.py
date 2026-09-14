from __future__ import annotations

from datetime import datetime, timezone

from src.newsroom_v3.production import run_once
from src.newsroom_v3.store import NewsroomV3Store


def test_ambiguous_publish_is_persisted_and_never_auto_retried(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    now = datetime.now(timezone.utc)
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    store.upsert_story(
        story_id="ambiguous-story",
        source_item_id="ambiguous-story",
        source="Reuters",
        source_url="https://example.com/ambiguous",
        title="Fresh Iran story",
        summary="Verified detail",
        published_at=now.isoformat(),
        fetched_at=now.isoformat(),
        media=[],
        source_priority="protected",
        fingerprint="fp-ambiguous",
        decision_state="ready",
        decision_reason="eligible",
    )
    store.close()

    first_calls = []
    first = run_once(
        data_dir=data_dir,
        fetchers=[],
        publisher=lambda story: first_calls.append(story.story_id)
        or {
            "ok": False,
            "error": "telegram_request_failed:TimeoutError",
            "ambiguous": True,
        },
        now=now,
        publish_enabled=True,
        min_publish_interval_seconds=0,
        retry_cooldown_seconds=0,
    )

    assert first["reason"] == "ambiguous_remote_state"
    assert first["telegram_writes"] == 0
    assert first_calls == ["ambiguous-story"]

    second_calls = []
    second = run_once(
        data_dir=data_dir,
        fetchers=[],
        publisher=lambda story: second_calls.append(story.story_id)
        or {"ok": True, "message_id": 2000},
        now=now,
        publish_enabled=True,
        min_publish_interval_seconds=0,
        retry_cooldown_seconds=0,
        max_attempts=99,
    )

    assert second["reason"] == "ambiguous_remote_state"
    assert second["telegram_writes"] == 0
    assert second_calls == []

    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    story = store.get_story("ambiguous-story")
    assert story is not None
    assert story.last_publish_error.startswith("ambiguous_remote_state:")
    assert len(store.list_publish_attempts("ambiguous-story")) == 1
    store.close()
