from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

from .managed_sources import fetch_managed_truth_items
from .managed_x_realtime import fetch_managed_x_realtime
from .newsroom_models import RawNewsItem
from .realtime_direct_sources import fetch_custom_nontelegram_realtime, fetch_priority_telegram_realtime
from .realtime_search import fetch_fresh_base_news_items, fetch_fresh_priority_news_items
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


def _published_dt(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(raw)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _wrap_news_fetcher(
    fetcher: Callable[[], list[NewsItem]],
    *,
    source_priority: str = "normal",
    max_age_hours: int | None = None,
):
    def wrapped() -> list[RawNewsItem]:
        now = datetime.now(timezone.utc)
        fetched_at = now.isoformat()
        out: list[RawNewsItem] = []
        for item in (fetcher() or []):
            if max_age_hours is not None:
                published = _published_dt(str(item.published or ""))
                if published is None:
                    continue
                age = now - published
                if age < timedelta(minutes=-10) or age > timedelta(hours=max_age_hours):
                    continue
            out.append(news_item_to_raw(item, fetched_at=fetched_at, source_priority=source_priority))
        return out

    return wrapped


def build_raw_fetchers(
    *,
    direct_x_fetch=fetch_managed_x_realtime,
    telegram_fetch=fetch_priority_telegram_realtime,
    custom_fetch=fetch_custom_nontelegram_realtime,
    base_fetch=fetch_fresh_base_news_items,
    priority_fetch=fetch_fresh_priority_news_items,
    truth_fetch=fetch_managed_truth_items,
):
    """Direct realtime lanes first; old search results are discarded before the newsroom sees them."""
    return [
        _wrap_news_fetcher(telegram_fetch, source_priority="protected"),
        _wrap_news_fetcher(direct_x_fetch, source_priority="protected"),
        truth_fetch,
        _wrap_news_fetcher(custom_fetch, source_priority="normal"),
        _wrap_news_fetcher(priority_fetch, source_priority="protected", max_age_hours=2),
        _wrap_news_fetcher(base_fetch, source_priority="normal", max_age_hours=2),
    ]
