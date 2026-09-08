from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .custom_sources import fetch_custom_news_items
from .editorial_rules import fetch_priority_news_items
from .newsroom_models import RawNewsItem
from .sources import NewsItem, fetch_news_items
from .truth_social import fetch_trump_truth_items


def news_item_to_raw(item: NewsItem, *, fetched_at: str | None = None, source_priority: str = "normal") -> RawNewsItem:
    return RawNewsItem(
        source=str(item.source or "").strip(),
        source_url=str(item.link or "").strip(),
        source_item_id=str(item.key or "").strip(),
        published_at=str(item.published or "").strip(),
        fetched_at=fetched_at or datetime.now(timezone.utc).isoformat(),
        title=str(item.title or "").strip(),
        summary=str(item.summary or "").strip(),
        media=[],
        source_priority=source_priority,
    )


def _wrap_news_fetcher(fetcher: Callable[[], list[NewsItem]], *, source_priority: str = "normal"):
    def wrapped() -> list[RawNewsItem]:
        fetched_at = datetime.now(timezone.utc).isoformat()
        return [news_item_to_raw(item, fetched_at=fetched_at, source_priority=source_priority) for item in (fetcher() or [])]

    return wrapped


def build_raw_fetchers(
    *,
    base_fetch=fetch_news_items,
    custom_fetch=fetch_custom_news_items,
    priority_fetch=fetch_priority_news_items,
    truth_fetch=fetch_trump_truth_items,
):
    return [
        _wrap_news_fetcher(base_fetch, source_priority="normal"),
        _wrap_news_fetcher(custom_fetch, source_priority="normal"),
        _wrap_news_fetcher(priority_fetch, source_priority="protected"),
        truth_fetch,
    ]
