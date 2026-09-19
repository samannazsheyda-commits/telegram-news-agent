from __future__ import annotations

import time

from src.newsroom_v5_store import NewsroomV5Store


def test_review_cursor_query_stays_bounded_with_two_thousand_stories(tmp_path):
    store = NewsroomV5Store(tmp_path / "newsroom.db")
    for index in range(2000):
        story_id = f"s-{index:04d}"
        store.upsert_story({
            "id": story_id,
            "news_key": story_id,
            "source_id": "src",
            "source_name": "Source",
            "source_url": f"https://example.test/{story_id}",
            "source_item_id": story_id,
            "original_title": story_id,
            "published_at_source": f"2026-09-{1 + index // 1440:02d}T{(index // 60) % 24:02d}:{index % 60:02d}:00+00:00",
            "state": "review",
        })
        store.set_translation(story_id, title_fa=f"خبر فارسی {index}", body_fa="متن", backend="test", quality_passed=True)

    started = time.perf_counter()
    page = store.list_review(limit=25)
    first_elapsed = time.perf_counter() - started
    assert len(page["items"]) == 25
    assert first_elapsed < 1.0

    cursor = page["next_cursor"]
    for _ in range(40):
        next_page = store.list_review(limit=25, cursor=cursor)
        cursor = next_page["next_cursor"]
        if not cursor:
            break
    started = time.perf_counter()
    later_page = store.list_review(limit=25, cursor=cursor) if cursor else {"items": []}
    later_elapsed = time.perf_counter() - started
    assert later_elapsed < 1.0
    assert len(later_page["items"]) <= 25


def test_review_payload_is_bounded_by_requested_page_size(tmp_path):
    store = NewsroomV5Store(tmp_path / "newsroom.db")
    for index in range(40):
        story_id = f"s-{index}"
        store.upsert_story({"id": story_id, "state": "review", "published_at_source": f"2026-09-20T10:{index:02d}:00+00:00"})
        store.set_translation(story_id, title_fa="خبر فارسی", body_fa="متن", backend="test", quality_passed=True)
    assert len(store.list_review(limit=17)["items"]) == 17
