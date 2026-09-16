from __future__ import annotations

import importlib

import pytest

from src.newsroom_v3.store import NewsroomV3Store


def _worker_class():
    try:
        module = importlib.import_module("src.newsroom_v3.outbox")
    except ModuleNotFoundError:
        pytest.fail("Newsroom V3 outbox worker is not implemented yet")
    return module.NewsroomV3PublisherWorker


def _seed_ready_story(store: NewsroomV3Store, story_id: str = "story-1") -> None:
    store.upsert_story(
        story_id=story_id,
        source_item_id=f"source-{story_id}",
        source="Reuters",
        source_url=f"https://example.com/{story_id}",
        title="Iran launches missiles during military exercise",
        summary="Material detail",
        published_at="2026-09-14T10:00:00+00:00",
        fingerprint=f"fp-{story_id}",
        decision_state="ready",
        decision_reason="eligible",
    )


def test_failed_publish_is_retried_then_success_is_idempotent(tmp_path):
    Worker = _worker_class()
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    _seed_ready_story(store)

    calls = []
    responses = iter(
        [
            {"ok": False, "error": "translation_or_format_failed"},
            {"ok": True, "message_id": 8123},
        ]
    )

    def publisher(story):
        calls.append(story.story_id)
        return next(responses)

    worker = Worker(store, publisher)

    first = worker.publish_story("story-1")
    assert first.state == "failed"
    assert store.get_story("story-1").decision_state == "ready"
    assert store.get_story("story-1").publish_state == "failed"

    second = worker.publish_story("story-1")
    assert second.state == "published"
    assert second.telegram_message_id == 8123
    assert store.get_story("story-1").telegram_message_id == 8123

    third = worker.publish_story("story-1")
    assert third.state == "already_published"
    assert calls == ["story-1", "story-1"]
    assert [(a.attempt_no, a.state) for a in store.list_publish_attempts("story-1")] == [
        (1, "failed"),
        (2, "published"),
    ]


def test_duplicate_event_is_terminal_and_never_requeued(tmp_path):
    Worker = _worker_class()
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    _seed_ready_story(store)

    calls = []

    def publisher(story):
        calls.append(story.story_id)
        return {"ok": False, "error": "duplicate_event"}

    worker = Worker(store, publisher)
    first = worker.publish_story("story-1")

    assert first.state == "duplicate_event"
    story = store.get_story("story-1")
    assert story.decision_state == "rejected"
    assert story.decision_reason == "publisher:duplicate_event"
    assert story.publish_state == "failed"
    assert store.list_publishable(limit=10) == []

    second = worker.publish_story("story-1")
    assert second.state == "not_publishable"
    assert calls == ["story-1"]
    assert [(a.attempt_no, a.state, a.error) for a in store.list_publish_attempts("story-1")] == [
        (1, "failed", "duplicate_event"),
    ]


def test_publisher_exception_is_persisted_without_changing_decision(tmp_path):
    Worker = _worker_class()
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    _seed_ready_story(store)

    def publisher(_story):
        raise RuntimeError("network down")

    result = Worker(store, publisher).publish_story("story-1")

    assert result.state == "failed"
    story = store.get_story("story-1")
    assert story.decision_state == "ready"
    assert story.publish_state == "failed"
    assert "RuntimeError" in story.last_publish_error
    attempts = store.list_publish_attempts("story-1")
    assert len(attempts) == 1
    assert attempts[0].state == "failed"
    assert "RuntimeError" in attempts[0].error


def test_worker_refuses_non_ready_editorial_state(tmp_path):
    Worker = _worker_class()
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    _seed_ready_story(store)
    story = store.get_story("story-1")
    store.upsert_story(
        story_id=story.story_id,
        source_item_id=story.source_item_id,
        source=story.source,
        source_url=story.source_url,
        title=story.title,
        summary=story.summary,
        published_at=story.published_at,
        fingerprint=story.fingerprint,
        decision_state="duplicate",
        decision_reason="duplicate_fingerprint",
        duplicate_of="canonical-1",
    )

    calls = []
    result = Worker(store, lambda _story: calls.append(True)) .publish_story("story-1")

    assert result.state == "not_publishable"
    assert calls == []
    assert store.list_publish_attempts("story-1") == []
