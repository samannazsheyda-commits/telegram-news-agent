from __future__ import annotations

import importlib

import pytest


def _store_class():
    try:
        module = importlib.import_module("src.newsroom_v3.store")
    except ModuleNotFoundError:
        pytest.fail("Newsroom V3 store is not implemented yet")
    return module.NewsroomV3Store


def _seed_ready_story(store) -> None:
    store.upsert_story(
        story_id="story-1",
        source_item_id="source-1",
        source="Reuters",
        source_url="https://example.com/story-1",
        title="A fresh story",
        summary="Material detail",
        published_at="2026-09-14T10:00:00+00:00",
        fingerprint="fp-1",
        decision_state="ready",
        decision_reason="eligible_unique",
    )


def test_publish_failure_does_not_poison_editorial_state_and_can_retry(tmp_path):
    NewsroomV3Store = _store_class()
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    _seed_ready_story(store)

    first_attempt = store.begin_publish("story-1")
    assert first_attempt.attempt_no == 1
    assert store.get_story("story-1").publish_state == "publishing"

    store.mark_publish_failed("story-1", "translation_or_format_failed")
    failed = store.get_story("story-1")
    assert failed.decision_state == "ready"
    assert failed.publish_state == "failed"
    assert failed.last_publish_error == "translation_or_format_failed"
    assert failed.telegram_message_id is None

    second_attempt = store.begin_publish("story-1")
    assert second_attempt.attempt_no == 2
    store.mark_published("story-1", telegram_message_id=4242)

    published = store.get_story("story-1")
    assert published.decision_state == "ready"
    assert published.publish_state == "published"
    assert published.last_publish_error == ""
    assert published.telegram_message_id == 4242

    attempts = store.list_publish_attempts("story-1")
    assert [(row.attempt_no, row.state) for row in attempts] == [
        (1, "failed"),
        (2, "published"),
    ]


def test_store_uses_wal_and_survives_reopen(tmp_path):
    NewsroomV3Store = _store_class()
    path = tmp_path / "newsroom-v3.sqlite3"

    store = NewsroomV3Store(path)
    _seed_ready_story(store)
    assert store.journal_mode().lower() == "wal"
    store.close()

    reopened = NewsroomV3Store(path)
    story = reopened.get_story("story-1")
    assert story is not None
    assert story.source == "Reuters"
    assert story.decision_state == "ready"
    assert story.publish_state == "not_attempted"
