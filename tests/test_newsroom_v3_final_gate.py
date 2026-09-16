from __future__ import annotations

from datetime import datetime, timezone

from src.newsroom_v3.final_gate import FinalGateDecision
from src.newsroom_v3.production import run_once
from src.newsroom_v3.store import NewsroomV3Store


def _ready_story(store: NewsroomV3Store, story_id: str, *, published_at: str, source: str = "Reuters"):
    store.upsert_story(
        story_id=story_id,
        source_item_id=story_id,
        source=source,
        source_url=f"https://example.com/{story_id}",
        title=f"Iran missile event {story_id}",
        summary="A concrete fresh event with a named actor and action.",
        published_at=published_at,
        fetched_at=published_at,
        media=[],
        source_priority="protected",
        fingerprint=f"fp-{story_id}",
        decision_state="ready",
        decision_reason="eligible",
    )


def test_final_gate_approval_allows_publish(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    now = datetime.now(timezone.utc)
    store = NewsroomV3Store(data / "newsroom_v3.sqlite3")
    _ready_story(store, "approved", published_at=now.isoformat())
    store.close()
    gate_calls = []
    telegram_calls = []

    def gate(story, recent):
        gate_calls.append((story.story_id, list(recent)))
        return FinalGateDecision(True, "factual_unique_event")

    result = run_once(
        data_dir=data,
        fetchers=[],
        publisher=lambda story: telegram_calls.append(story.story_id) or {"ok": True, "message_id": 2001},
        final_gate=gate,
        now=now,
        min_publish_interval_seconds=0,
    )

    assert result["reason"] == "published"
    assert result["telegram_writes"] == 1
    assert gate_calls[0][0] == "approved"
    assert telegram_calls == ["approved"]


def test_final_gate_rejection_is_persisted_and_never_sent(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    now = datetime.now(timezone.utc)
    store = NewsroomV3Store(data / "newsroom_v3.sqlite3")
    _ready_story(store, "analysis-story", published_at=now.isoformat())
    store.close()
    telegram_calls = []

    result = run_once(
        data_dir=data,
        fetchers=[],
        publisher=lambda story: telegram_calls.append(story.story_id),
        final_gate=lambda story, recent: FinalGateDecision(False, "analysis_or_report"),
        now=now,
        min_publish_interval_seconds=0,
    )

    assert result["reason"] == "final_gate_rejected"
    assert result["telegram_writes"] == 0
    assert telegram_calls == []
    store = NewsroomV3Store(data / "newsroom_v3.sqlite3")
    persisted = store.get_story("analysis-story")
    store.close()
    assert persisted is not None
    assert persisted.decision_state == "rejected"
    assert persisted.decision_reason == "final_gate:analysis_or_report"


def test_final_gate_exception_fails_closed_without_telegram_write(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    now = datetime.now(timezone.utc)
    store = NewsroomV3Store(data / "newsroom_v3.sqlite3")
    _ready_story(store, "gate-error", published_at=now.isoformat())
    store.close()
    telegram_calls = []

    def broken_gate(story, recent):
        raise RuntimeError("provider timeout")

    result = run_once(
        data_dir=data,
        fetchers=[],
        publisher=lambda story: telegram_calls.append(story.story_id),
        final_gate=broken_gate,
        now=now,
        min_publish_interval_seconds=0,
    )

    assert result["reason"] == "final_gate_error"
    assert result["telegram_writes"] == 0
    assert telegram_calls == []


def test_final_gate_receives_recent_published_context_for_semantic_dedup(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    now = datetime.now(timezone.utc)
    store = NewsroomV3Store(data / "newsroom_v3.sqlite3")
    _ready_story(store, "already-live", published_at=now.isoformat())
    store.begin_publish("already-live")
    store.mark_published("already-live", telegram_message_id=1999)
    _ready_story(store, "same-event-new-source", published_at=now.isoformat(), source="Clash Report")
    store.close()
    seen_recent = []

    def gate(story, recent):
        seen_recent.extend(recent)
        return FinalGateDecision(False, "duplicate_event")

    result = run_once(
        data_dir=data,
        fetchers=[],
        publisher=lambda story: {"ok": True, "message_id": 2002},
        final_gate=gate,
        now=now,
        min_publish_interval_seconds=0,
    )

    assert result["reason"] == "final_gate_rejected"
    assert any(story.story_id == "already-live" for story in seen_recent)


def test_daily_limit_blocks_26th_story_before_gate_and_telegram(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    now = datetime.now(timezone.utc)
    store = NewsroomV3Store(data / "newsroom_v3.sqlite3")
    for index in range(25):
        story_id = f"published-{index}"
        _ready_story(store, story_id, published_at=now.isoformat())
        store.begin_publish(story_id)
        store.mark_published(story_id, telegram_message_id=3000 + index)
    _ready_story(store, "twenty-six", published_at=now.isoformat())
    store.close()
    gate_calls = []
    telegram_calls = []

    result = run_once(
        data_dir=data,
        fetchers=[],
        publisher=lambda story: telegram_calls.append(story.story_id),
        final_gate=lambda story, recent: gate_calls.append(story.story_id) or FinalGateDecision(True, "ok"),
        now=now,
        min_publish_interval_seconds=0,
        daily_limit=25,
    )

    assert result["reason"] == "daily_limit"
    assert result["daily_published"] == 25
    assert result["daily_limit"] == 25
    assert result["telegram_writes"] == 0
    assert gate_calls == []
    assert telegram_calls == []
