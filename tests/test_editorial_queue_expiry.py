from datetime import datetime, timezone

from src.editorial_store import LocalEditorialStore, ReviewItem
from src.runtime_v13 import expire_previous_day_queue


def test_expire_previous_day_queue_moves_old_items_to_history(tmp_path):
    store = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")
    old = ReviewItem.for_news(
        news_key="old-news",
        source="Reuters / X",
        source_url="https://x.com/Reuters/status/1",
        original_title="Old",
        persian_title="خبر دیروز",
        published_at_source="Sun, 06 Sep 2026 08:00:00 +0000",
    )
    today = ReviewItem.for_news(
        news_key="today-news",
        source="Reuters / X",
        source_url="https://x.com/Reuters/status/2",
        original_title="Today",
        persian_title="خبر امروز",
        published_at_source="Mon, 07 Sep 2026 08:00:00 +0000",
    )
    store.upsert_queue(old)
    store.upsert_queue(today)

    moved = expire_previous_day_queue(
        datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
        store=store,
    )

    assert moved == 1
    assert store.get_pending(old.id) is None
    assert store.get_pending(today.id) is not None
    old_history = next(x for x in store.history() if x["id"] == old.id)
    assert old_history["status"] == "superseded"


def test_expire_previous_day_queue_keeps_unknown_timestamp_for_manual_review(tmp_path):
    store = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")
    item = ReviewItem.for_news(
        news_key="unknown-time",
        source="Test",
        source_url="https://example.com/1",
        original_title="Unknown",
        persian_title="زمان نامشخص",
        published_at_source="",
    )
    store.upsert_queue(item)

    moved = expire_previous_day_queue(
        datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
        store=store,
    )

    assert moved == 0
    assert store.get_pending(item.id) is not None
