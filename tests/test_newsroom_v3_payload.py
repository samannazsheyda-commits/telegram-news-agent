from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pytest

from src.newsroom_models import RawNewsItem
from src.newsroom_v3.shadow import NewsroomV3ShadowPipeline
from src.newsroom_v3.store import NewsroomV3Store


def _adapter_class():
    try:
        module = importlib.import_module("src.newsroom_v3.publisher_adapter")
    except ModuleNotFoundError:
        pytest.fail("Newsroom V3 publisher adapter is not implemented yet")
    return module.V3TelegramPublisherAdapter


def test_shadow_store_preserves_media_and_raw_publish_context(tmp_path):
    store = NewsroomV3Store(tmp_path / "newsroom_v3.sqlite3")
    raw = RawNewsItem(
        source="Reuters",
        source_url="https://www.reuters.com/world/middle-east/iran-drone-strike/",
        source_item_id="reuters-media-1",
        published_at="2026-09-14T10:00:00+00:00",
        fetched_at="2026-09-14T10:04:30+00:00",
        title="Iran launches drone during military exercise near Strait of Hormuz",
        summary="Iranian forces launched a drone during an exercise near the Strait of Hormuz.",
        media=[
            {"type": "image", "url": "https://cdn.example.com/photo.jpg"},
            {"type": "video", "url": "https://cdn.example.com/video.mp4"},
        ],
        source_priority="protected",
    )

    result = NewsroomV3ShadowPipeline(store).run(
        [raw],
        now=datetime(2026, 9, 14, 10, 5, tzinfo=timezone.utc),
    )
    story_id = result.story_ids[0]
    store.close()

    reopened = NewsroomV3Store(tmp_path / "newsroom_v3.sqlite3")
    story = reopened.get_story(story_id)
    assert story.fetched_at == raw.fetched_at
    assert story.media == raw.media
    assert story.source_priority == "protected"


def test_v3_adapter_reconstructs_normalized_item_for_existing_strict_publisher(tmp_path):
    Adapter = _adapter_class()
    store = NewsroomV3Store(tmp_path / "newsroom_v3.sqlite3")
    store.upsert_story(
        story_id="story-media",
        source_item_id="source-media",
        source="Reuters",
        source_url="https://example.com/story-media",
        title="Iran launches drone during military exercise",
        summary="Iranian forces launched a drone during an exercise.",
        published_at="2026-09-14T10:00:00+00:00",
        fetched_at="2026-09-14T10:04:00+00:00",
        media=[{"type": "image", "url": "https://cdn.example.com/photo.jpg"}],
        source_priority="protected",
        fingerprint="fp-media",
        decision_state="ready",
        decision_reason="eligible",
    )
    story = store.get_story("story-media")
    captured = []

    def strict_publisher(item):
        captured.append(item)
        return {"ok": True, "message_id": 31337}

    result = Adapter(strict_publisher)(story)

    assert result == {"ok": True, "message_id": 31337}
    assert len(captured) == 1
    item = captured[0]
    assert item.raw.source == "Reuters"
    assert item.raw.source_item_id == "source-media"
    assert item.raw.media == [{"type": "image", "url": "https://cdn.example.com/photo.jpg"}]
    assert item.raw.source_priority == "protected"
