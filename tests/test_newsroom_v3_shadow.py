from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pytest

from src.newsroom_models import RawNewsItem
from src.newsroom_v3.store import NewsroomV3Store


def _pipeline_class():
    try:
        module = importlib.import_module("src.newsroom_v3.shadow")
    except ModuleNotFoundError:
        pytest.fail("Newsroom V3 shadow pipeline is not implemented yet")
    return module.NewsroomV3ShadowPipeline


def test_shadow_pipeline_persists_ready_story_without_telegram_write(tmp_path):
    NewsroomV3ShadowPipeline = _pipeline_class()
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    now = datetime(2026, 9, 14, 10, 5, tzinfo=timezone.utc)
    raw = RawNewsItem(
        source="Reuters",
        source_url="https://www.reuters.com/world/middle-east/iran-missile-launch-2026-09-14/",
        source_item_id="reuters-iran-missile-launch",
        published_at="2026-09-14T10:00:00+00:00",
        fetched_at="2026-09-14T10:04:00+00:00",
        title="Iran launches missiles during military exercise near Strait of Hormuz",
        summary="Iranian forces launched missiles during a military exercise near the Strait of Hormuz.",
    )

    result = NewsroomV3ShadowPipeline(store).run([raw], now=now)

    assert result.processed == 1
    assert result.ready == 1
    assert result.telegram_writes == 0
    assert len(result.story_ids) == 1

    story = store.get_story(result.story_ids[0])
    assert story is not None
    assert story.decision_state == "ready"
    assert story.decision_reason == "eligible"
    assert story.publish_state == "not_attempted"
    assert story.telegram_message_id is None


def test_shadow_pipeline_records_rejection_without_starting_publish(tmp_path):
    NewsroomV3ShadowPipeline = _pipeline_class()
    store = NewsroomV3Store(tmp_path / "newsroom-v3.sqlite3")
    now = datetime(2026, 9, 14, 10, 5, tzinfo=timezone.utc)
    raw = RawNewsItem(
        source="Reuters",
        source_url="https://www.reuters.com/world/europe/old-story/",
        source_item_id="reuters-old-story",
        published_at="2026-09-13T10:00:00+00:00",
        fetched_at="2026-09-14T10:04:00+00:00",
        title="Iran missile report from previous day",
        summary="An old report about an Iranian missile event.",
    )

    result = NewsroomV3ShadowPipeline(store).run([raw], now=now)

    assert result.processed == 1
    assert result.rejected == 1
    assert result.telegram_writes == 0

    story = store.get_story(result.story_ids[0])
    assert story is not None
    assert story.decision_state == "rejected"
    assert story.decision_reason == "stale"
    assert story.publish_state == "not_attempted"
    assert store.list_publish_attempts(story.story_id) == []
