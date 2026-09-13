from __future__ import annotations

from src.newsroom_v3.store import NewsroomV3Store


def _seed(store, *, state="waiting"):
    store.upsert_story(
        story_id="story-1",
        source_item_id="source-1",
        source="Reuters",
        source_url="https://example.com/story-1",
        title="Iran launches missiles during military exercise",
        summary="Material detail",
        published_at="2026-09-14T10:00:00+00:00",
        fingerprint="fp-1",
        decision_state=state,
        decision_reason="needs_editorial_review" if state == "waiting" else "eligible",
    )


def test_editorial_approval_changes_only_decision_state(tmp_path):
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    _seed(store)

    updated = store.set_decision("story-1", "ready", reason="editor_approved")

    assert updated.decision_state == "ready"
    assert updated.decision_reason == "editor_approved"
    assert updated.duplicate_of == ""
    assert updated.publish_state == "not_attempted"
    assert store.list_publish_attempts("story-1") == []


def test_editorial_change_after_publish_failure_preserves_retry_history(tmp_path):
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    _seed(store, state="ready")
    store.begin_publish("story-1")
    store.mark_publish_failed("story-1", "temporary_failure")

    rejected = store.set_decision("story-1", "rejected", reason="editor_rejected")
    assert rejected.decision_state == "rejected"
    assert rejected.publish_state == "failed"
    assert rejected.last_publish_error == "temporary_failure"
    assert [(a.attempt_no, a.state) for a in store.list_publish_attempts("story-1")] == [(1, "failed")]

    restored = store.set_decision("story-1", "ready", reason="editor_restored")
    assert restored.decision_state == "ready"
    assert restored.publish_state == "failed"
    second = store.begin_publish("story-1")
    assert second.attempt_no == 2
