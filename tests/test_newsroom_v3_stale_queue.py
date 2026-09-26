from datetime import datetime, timedelta, timezone

from src.event_ledger import EventLedger
from src.newsroom_v3.production import _candidate_for_publish, _safe_candidates
from src.newsroom_v3.store import NewsroomV3Store


NOW = datetime(2026, 9, 26, 16, 20, tzinfo=timezone.utc)


def _insert(store: NewsroomV3Store, story_id: str, *, published_at: datetime) -> None:
    store.upsert_story(
        story_id=story_id,
        source_item_id=story_id,
        source="Reuters",
        source_url=f"https://example.com/{story_id}",
        title=f"Iran missile update {story_id}",
        summary="Fresh verified detail.",
        published_at=published_at.isoformat(),
        fetched_at=published_at.isoformat(),
        media=[],
        source_priority="normal",
        fingerprint=f"fp-{story_id}",
        decision_state="ready",
        decision_reason="eligible",
    )


def test_stale_ready_backlog_does_not_hide_fresh_candidate(tmp_path):
    store = NewsroomV3Store(tmp_path / "newsroom_v3.sqlite3")
    for index in range(120):
        _insert(store, f"old-{index:04d}", published_at=NOW - timedelta(days=3))
    _insert(store, "fresh-today", published_at=NOW - timedelta(minutes=20))
    ledger = EventLedger(tmp_path / "event_ledger.json")

    safe = _safe_candidates(store, ledger, now=NOW)
    story, reason = _candidate_for_publish(
        store,
        ledger,
        now=NOW,
        retry_cooldown_seconds=300,
        max_attempts=3,
    )

    assert [row.story_id for row in safe] == ["fresh-today"]
    assert reason == "safe_candidate"
    assert story is not None
    assert story.story_id == "fresh-today"
    store.close()
