from __future__ import annotations

from datetime import datetime, timezone

from src.newsroom_models import RawNewsItem
from src.newsroom_v3.shadow import NewsroomV3ShadowPipeline, _story_id
from src.newsroom_v3.store import NewsroomV3Store
from src.operator_blocks import add_operator_block


def _raw() -> RawNewsItem:
    return RawNewsItem(
        source="Reuters",
        source_item_id="operator-block-1",
        source_url="https://example.com/operator-block-1",
        title="Iran announces a new economic measure",
        summary="Officials announced a new economic measure on Friday.",
        published_at="2026-09-18T10:00:00+00:00",
        fetched_at="2026-09-18T10:01:00+00:00",
        media=[],
        source_priority="normal",
    )


def test_operator_block_remains_terminal_after_reingest(tmp_path):
    store = NewsroomV3Store(tmp_path / "newsroom.sqlite3")
    pipeline = NewsroomV3ShadowPipeline(store)
    raw = _raw()
    now = datetime(2026, 9, 18, 10, 5, tzinfo=timezone.utc)

    pipeline.run([raw], now=now)
    story_id = _story_id(raw)
    store.set_decision(story_id, "rejected", reason="operator_block:requested_by_admin")

    pipeline.run([raw], now=now)
    story = store.get_story(story_id)

    assert story is not None
    assert story.decision_state == "rejected"
    assert story.decision_reason == "operator_block:requested_by_admin"
    store.close()


def test_operator_block_registry_rejects_story_when_seen_again(tmp_path):
    store = NewsroomV3Store(tmp_path / "newsroom.sqlite3")
    pipeline = NewsroomV3ShadowPipeline(store)
    raw = _raw()
    now = datetime(2026, 9, 18, 10, 5, tzinfo=timezone.utc)

    add_operator_block(
        tmp_path / "operator_blocks.json",
        story_id="manual-panel-id",
        source_url=raw.source_url,
        fingerprint="",
        title=raw.title,
        reason="requested_by_admin",
    )

    result = pipeline.run([raw], now=now)
    story = store.get_story(_story_id(raw))

    assert result.rejected == 1
    assert story is not None
    assert story.decision_state == "rejected"
    assert story.decision_reason == "operator_block:requested_by_admin"
    store.close()
