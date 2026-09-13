from __future__ import annotations

from datetime import datetime, timezone

from src.newsroom_models import RawNewsItem
from src.newsroom_v3.shadow import NewsroomV3ShadowPipeline
from src.newsroom_v3.store import NewsroomV3Store


def _raw(*, source: str, source_url: str, source_item_id: str) -> RawNewsItem:
    return RawNewsItem(
        source=source,
        source_url=source_url,
        source_item_id=source_item_id,
        published_at="2026-09-14T10:00:00+00:00",
        fetched_at="2026-09-14T10:04:00+00:00",
        title="Iran launches missiles during military exercise near Strait of Hormuz",
        summary="Iranian forces launched missiles during a military exercise near the Strait of Hormuz.",
    )


def test_same_fingerprint_from_second_source_is_durable_duplicate(tmp_path):
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    now = datetime(2026, 9, 14, 10, 5, tzinfo=timezone.utc)
    first = _raw(
        source="Reuters",
        source_url="https://www.reuters.com/world/middle-east/iran-missile-launch/",
        source_item_id="reuters-1",
    )
    second = _raw(
        source="AP",
        source_url="https://apnews.com/article/iran-missile-launch-1",
        source_item_id="ap-1",
    )

    result = NewsroomV3ShadowPipeline(store).run([first, second], now=now)

    assert result.processed == 2
    assert result.ready == 1
    assert result.duplicates == 1
    assert result.telegram_writes == 0

    canonical = store.get_story(result.story_ids[0])
    duplicate = store.get_story(result.story_ids[1])
    assert canonical is not None and duplicate is not None
    assert canonical.decision_state == "ready"
    assert duplicate.decision_state == "duplicate"
    assert duplicate.decision_reason == "duplicate_fingerprint"
    assert duplicate.duplicate_of == canonical.story_id
    assert duplicate.publish_state == "not_attempted"


def test_duplicate_ingest_does_not_overwrite_failed_canonical_publish_state(tmp_path):
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    pipeline = NewsroomV3ShadowPipeline(store)
    now = datetime(2026, 9, 14, 10, 5, tzinfo=timezone.utc)
    first = _raw(
        source="Reuters",
        source_url="https://www.reuters.com/world/middle-east/iran-missile-launch/",
        source_item_id="reuters-1",
    )
    first_result = pipeline.run([first], now=now)
    canonical_id = first_result.story_ids[0]

    store.begin_publish(canonical_id)
    store.mark_publish_failed(canonical_id, "temporary_telegram_failure")

    second = _raw(
        source="AP",
        source_url="https://apnews.com/article/iran-missile-launch-1",
        source_item_id="ap-1",
    )
    result = pipeline.run([second], now=now)

    assert result.duplicates == 1
    canonical = store.get_story(canonical_id)
    duplicate = store.get_story(result.story_ids[0])
    assert canonical.decision_state == "ready"
    assert canonical.publish_state == "failed"
    assert canonical.last_publish_error == "temporary_telegram_failure"
    assert duplicate.decision_state == "duplicate"
    assert duplicate.duplicate_of == canonical_id
