from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .custom_sources import fetch_custom_news_items
from .fresh_x import fetch_fresh_x_news_items
from .managed_sources import fetch_managed_base_news_items, fetch_managed_priority_news_items, fetch_managed_truth_items
from .newsroom_models import RawNewsItem
from .sources import NewsItem


def _media_from_news_item(item: NewsItem) -> list[dict[str, str]]:
    media: list[dict[str, str]] = []
    video_url = str(getattr(item, "video_url", "") or "").strip()
    image_url = str(getattr(item, "media_url", "") or "").strip()
    if video_url.startswith("https://"):
        media.append({"type": "video", "url": video_url})
    if image_url.startswith("https://"):
        media.append({"type": "image", "url": image_url})
    return media


def news_item_to_raw(item: NewsItem, *, fetched_at: str | None = None, source_priority: str = "normal") -> RawNewsItem:
    return RawNewsItem(
        source=str(item.source or "").strip(),
        source_url=str(item.link or "").strip(),
        source_item_id=str(item.key or "").strip(),
        published_at=str(item.published or "").strip(),
        fetched_at=fetched_at or datetime.now(timezone.utc).isoformat(),
        title=str(item.title or "").strip(),
        summary=str(item.summary or "").strip(),
        media=_media_from_news_item(item),
        source_priority=source_priority,
    )


def _wrap_news_fetcher(fetcher: Callable[[], list[NewsItem]], *, source_priority: str = "normal"):
    def wrapped() -> list[RawNewsItem]:
        fetched_at = datetime.now(timezone.utc).isoformat()
        return [news_item_to_raw(item, fetched_at=fetched_at, source_priority=source_priority) for item in (fetcher() or [])]

    return wrapped


def build_raw_fetchers(
    *,
    direct_x_fetch=fetch_fresh_x_news_items,
    base_fetch=fetch_managed_base_news_items,
    custom_fetch=fetch_custom_news_items,
    priority_fetch=fetch_managed_priority_news_items,
    truth_fetch=fetch_managed_truth_items,
):
    """Build independent realtime lanes, with direct sources ahead of search fallbacks.

    FxTwitter returns canonical X post URLs/timestamps and is therefore a true
    realtime source. Google/system query lanes remain available as discovery
    fallbacks, but they can no longer be the only path for monitored X accounts.
    """
    return [
        _wrap_news_fetcher(direct_x_fetch, source_priority="protected"),
        _wrap_news_fetcher(custom_fetch, source_priority="normal"),
        truth_fetch,
        _wrap_news_fetcher(priority_fetch, source_priority="protected"),
        _wrap_news_fetcher(base_fetch, source_priority="normal"),
    ]
