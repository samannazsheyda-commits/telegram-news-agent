from datetime import datetime, timezone

from src.newsroom_v3.publication_policy import count_successful_publications
from src.newsroom_v3.store import NewsroomV3Store


def _story(store: NewsroomV3Store, story_id: str):
    now = datetime.now(timezone.utc).isoformat()
    store.upsert_story(
        story_id=story_id,
        source_item_id=story_id,
        source="Reuters",
        source_url=f"https://example.com/{story_id}",
        title="Iran missile event",
        summary="A concrete event.",
        published_at=now,
        fetched_at=now,
        media=[],
        source_priority="protected",
        fingerprint=f"fp-{story_id}",
        decision_state="ready",
        decision_reason="eligible",
    )


def test_daily_count_resets_at_tehran_midnight(tmp_path):
    store = NewsroomV3Store(tmp_path / "newsroom.sqlite3")
    _story(store, "before-midnight")
    store.begin_publish("before-midnight")
    store.mark_published("before-midnight", telegram_message_id=1)
    with store._conn:
        store._conn.execute(
            "UPDATE publish_attempts SET finished_at=? WHERE story_id=?",
            ("2026-09-16T20:20:00+00:00", "before-midnight"),
        )

    before = datetime(2026, 9, 16, 20, 29, tzinfo=timezone.utc)  # 23:59 Tehran
    after = datetime(2026, 9, 16, 20, 31, tzinfo=timezone.utc)   # 00:01 Tehran next day
    assert count_successful_publications(store, now=before) == 1
    assert count_successful_publications(store, now=after) == 0
    store.close()


def test_failed_publish_attempt_does_not_consume_daily_slot(tmp_path):
    store = NewsroomV3Store(tmp_path / "newsroom.sqlite3")
    _story(store, "failed")
    store.begin_publish("failed")
    store.mark_publish_failed("failed", "telegram_timeout")

    assert count_successful_publications(store, now=datetime.now(timezone.utc)) == 0
    store.close()
