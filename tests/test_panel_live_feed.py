from datetime import datetime, timedelta, timezone

from src.newsroom_models import LiveFeedRecord
from src.panel_live_feed import LiveFeedStore


def record(item_id: str, *, status="new", event_id="event-1", updated_at="2026-09-07T12:00:00+00:00"):
    return LiveFeedRecord(
        item_id=item_id,
        event_id=event_id,
        source="Reuters",
        source_url=f"https://example.com/{item_id}",
        title=f"Story {item_id}",
        published_at_source=updated_at,
        discovered_at=updated_at,
        decision=status,
        decision_reason="test",
        duplicate_of="",
        telegram_message_id=777 if status == "auto_published" else None,
        panel_status=status,
        updated_at=updated_at,
    )


def test_store_supports_all_panel_statuses(tmp_path):
    store = LiveFeedStore(tmp_path / "feed.json")
    statuses = ["new", "auto_published", "waiting", "duplicate", "rejected", "failed"]
    for index, status in enumerate(statuses):
        store.upsert(record(str(index), status=status, event_id=f"event-{index}"))
    assert {row.panel_status for row in store.records()} == set(statuses)


def test_upsert_replaces_same_item_id(tmp_path):
    store = LiveFeedStore(tmp_path / "feed.json")
    store.upsert(record("a", status="new"))
    store.upsert(record("a", status="auto_published"))
    rows = store.records()
    assert len(rows) == 1
    assert rows[0].panel_status == "auto_published"
    assert rows[0].telegram_message_id == 777


def test_same_event_from_different_sources_remains_visible_as_two_items(tmp_path):
    store = LiveFeedStore(tmp_path / "feed.json")
    store.upsert(record("a", status="auto_published", event_id="event-x", updated_at="2026-09-07T12:00:00+00:00"))
    store.upsert(record("b", status="duplicate", event_id="event-x", updated_at="2026-09-07T12:05:00+00:00"))
    rows = store.records()
    assert len(rows) == 2
    assert {row.item_id for row in rows} == {"a", "b"}
    assert {row.panel_status for row in rows} == {"auto_published", "duplicate"}


def test_prune_removes_stale_records_and_enforces_cap(tmp_path):
    store = LiveFeedStore(tmp_path / "feed.json")
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    old = (now - timedelta(hours=8)).isoformat()
    for index in range(5):
        ts = (now - timedelta(minutes=index)).isoformat()
        store.upsert(record(f"fresh-{index}", event_id=f"fresh-event-{index}", updated_at=ts))
    store.upsert(record("old", event_id="old-event", updated_at=old))
    store.prune(now, freshness_hours=3, max_records=3)
    rows = store.records()
    assert len(rows) == 3
    assert all(row.item_id != "old" for row in rows)
    assert [row.item_id for row in rows] == ["fresh-0", "fresh-1", "fresh-2"]


def test_auto_published_item_remains_visible_in_live_feed(tmp_path):
    store = LiveFeedStore(tmp_path / "feed.json")
    store.upsert(record("published", status="auto_published"))
    assert [row.panel_status for row in store.records()] == ["auto_published"]
