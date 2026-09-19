from __future__ import annotations

from src.newsroom_v5_events import NewsroomEventBroker
from src.newsroom_v5_publish import prepare_publication, process_publication
from src.newsroom_v5_store import NewsroomV5Store


def test_successful_publish_emits_story_published_after_state_commit(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    store.upsert_story({
        "id": "s1", "news_key": "s1", "source_id": "src", "source_name": "Source",
        "source_url": "https://example.test/s1", "source_item_id": "s1",
        "original_title": "Original", "published_at_source": "2026-09-20T10:00:00+00:00", "state": "review",
    })
    store.set_translation("s1", title_fa="تیتر فارسی", body_fa="متن فارسی", backend="test", quality_passed=True)
    publication = prepare_publication(store, "s1", idempotency_key="publish:s1")
    broker = NewsroomEventBroker(max_events=10)

    result = process_publication(
        store,
        publication["id"],
        sender=lambda _title, _body: 321,
        event_sink=broker.publish,
    )

    assert result["status"] == "published"
    events = broker.snapshot()
    assert [event.type for event in events] == ["story_published", "counts_changed"]
    assert events[0].payload["story_id"] == "s1"
    assert events[0].payload["telegram_message_id"] == "321"
    assert store.get_story("s1")["state"] == "published"
