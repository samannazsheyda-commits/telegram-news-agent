from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from src.newsroom_raw_intake import _wrap_news_fetcher, build_raw_fetchers
from src.realtime_direct_sources import _priority_relevant
from src.sources import NewsItem


def test_priority_telegram_accepts_regional_missile_alert_without_explicit_iran_word():
    assert _priority_relevant("Ballistic missile intercept reported over Israel after launch toward the region") is True
    assert _priority_relevant("Explosion reported near the Strait of Hormuz") is True


def test_priority_telegram_rejects_unrelated_global_war_item():
    assert _priority_relevant("Missile test announced in the Pacific") is False


def test_search_fallback_wrapper_drops_old_items_before_cycle():
    now = datetime.now(timezone.utc)
    old = NewsItem("old", "Reuters", "old", "", "https://example.com/old", format_datetime(now - timedelta(days=3)))
    fresh = NewsItem("fresh", "Reuters", "fresh", "", "https://example.com/fresh", format_datetime(now - timedelta(minutes=20)))
    wrapped = _wrap_news_fetcher(lambda: [old, fresh], max_age_hours=2)
    rows = wrapped()
    assert [row.source_item_id for row in rows] == ["fresh"]


def test_direct_telegram_is_first_realtime_lane():
    marker = NewsItem("tg", "Telegram", "Iran missile launch", "", "https://t.me/test/1", format_datetime(datetime.now(timezone.utc)))
    fetchers = build_raw_fetchers(
        telegram_fetch=lambda: [marker],
        direct_x_fetch=lambda: [],
        custom_fetch=lambda: [],
        truth_fetch=lambda: [],
        priority_fetch=lambda: [],
        base_fetch=lambda: [],
    )
    first = fetchers[0]()
    assert first and first[0].source_item_id == "tg"
    assert first[0].source_priority == "protected"
