from __future__ import annotations

from ..newsroom_models import RawNewsItem
from ..newsroom_normalize import normalize_item
from .store import StoryRecord


class V3TelegramPublisherAdapter:
    """Adapt a durable V3 StoryRecord to the existing guarded publisher API."""

    def __init__(self, publisher):
        self.publisher = publisher

    def __call__(self, story: StoryRecord):
        raw = RawNewsItem(
            source=story.source,
            source_url=story.source_url,
            source_item_id=story.source_item_id,
            published_at=story.published_at,
            fetched_at=story.fetched_at or story.created_at,
            title=story.title,
            summary=story.summary,
            media=list(story.media or []),
            source_priority=story.source_priority or "normal",
        )
        return self.publisher(normalize_item(raw))
