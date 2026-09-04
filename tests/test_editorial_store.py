from __future__ import annotations

from dataclasses import asdict

from src.editorial_store import LocalEditorialStore, ReviewItem, merge_record_sets


def test_merge_preserves_unrelated_remote_and_local_records():
    remote = [{"id": "a", "status": "pending", "updated_at": "2026-09-05T00:00:00+00:00"}]
    local = [{"id": "b", "status": "pending", "updated_at": "2026-09-05T00:01:00+00:00"}]
    merged = merge_record_sets(remote, local)
    assert {r["id"] for r in merged} == {"a", "b"}


def test_same_id_prefers_newer_decision_record():
    remote = [{"id": "a", "status": "pending", "updated_at": "2026-09-05T00:00:00+00:00"}]
    local = [{"id": "a", "status": "published_manual", "updated_at": "2026-09-05T00:01:00+00:00"}]
    merged = merge_record_sets(remote, local)
    assert merged[0]["status"] == "published_manual"


def test_review_item_id_is_deterministic_from_news_key():
    first = ReviewItem.for_news(
        news_key="abc123",
        source="Reuters",
        source_url="https://example.com/a",
        original_title="Title",
    )
    second = ReviewItem.for_news(
        news_key="abc123",
        source="Reuters",
        source_url="https://example.com/a",
        original_title="Title",
    )
    assert first.id == second.id


def test_local_store_upserts_and_moves_item(tmp_path):
    store = LocalEditorialStore(
        queue_path=tmp_path / "queue.json",
        history_path=tmp_path / "history.json",
    )
    item = ReviewItem.for_news(
        news_key="story-1",
        source="Reuters",
        source_url="https://example.com/1",
        original_title="Iran story",
        rejection_reason="article_or_commentary",
    )
    store.upsert_queue(item)
    assert store.get_pending(item.id).news_key == "story-1"

    moved = store.move_to_history(
        item.id,
        status="rejected_manual",
        final_persian_title="رد شد",
        final_persian_body="",
    )
    assert moved.status == "rejected_manual"
    assert store.get_pending(item.id) is None
    assert store.history()[0]["id"] == item.id


def test_local_store_round_trips_full_record(tmp_path):
    store = LocalEditorialStore(
        queue_path=tmp_path / "queue.json",
        history_path=tmp_path / "history.json",
    )
    item = ReviewItem.for_news(
        news_key="story-2",
        source="The New York Times",
        source_url="https://example.com/2",
        original_title="Original",
        original_summary="Summary",
        persian_title="تیتر",
        persian_body="متن",
        published_at_source="Fri, 05 Sep 2026 10:00:00 GMT",
        rejection_reason="low_signal",
    )
    store.upsert_queue(item)
    assert asdict(store.get_pending(item.id)) == asdict(item)
