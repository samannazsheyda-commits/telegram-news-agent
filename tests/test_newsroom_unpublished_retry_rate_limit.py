from datetime import datetime, timezone

from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore


NOW = datetime(2026, 9, 13, 5, 40, tzinfo=timezone.utc)


def _item(item_id: str, title: str) -> RawNewsItem:
    return RawNewsItem(
        source="Reuters",
        source_url=f"https://example.com/{item_id}",
        source_item_id=item_id,
        published_at="2026-09-13T05:35:00+00:00",
        fetched_at="2026-09-13T05:36:00+00:00",
        title=title,
        source_priority="normal",
    )


def _stores(tmp_path):
    return (
        EventLedger(tmp_path / "ledger.json"),
        LiveFeedStore(tmp_path / "live.json"),
        LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json"),
    )


def test_unpublished_retry_is_not_blocked_by_hourly_cap(tmp_path):
    ledger, live, editorial = _stores(tmp_path)
    failed = _item("failed", "Iran partially reopens airspace to international flights")
    filler = _item("filler", "Iran announces new restricted zone outside Strait of Hormuz")

    first = run_cycle(
        fetcher=lambda: [failed],
        ledger=ledger,
        live_feed=live,
        editorial_store=editorial,
        publisher=lambda item: {"ok": False},
        settings={"auto_publish": True, "hourly_news_limit": 1},
        now=NOW,
    )
    assert first.publish_failed == 1

    second = run_cycle(
        fetcher=lambda: [filler],
        ledger=ledger,
        live_feed=live,
        editorial_store=editorial,
        publisher=lambda item: {"ok": True, "message_id": 700},
        settings={"auto_publish": True, "hourly_news_limit": 1},
        now=NOW,
    )
    assert second.published == 1

    sent = []
    retry = run_cycle(
        fetcher=lambda: [failed],
        ledger=ledger,
        live_feed=live,
        editorial_store=editorial,
        publisher=lambda item: sent.append(item.raw.source_item_id) or {"ok": True, "message_id": 701},
        settings={"auto_publish": True, "hourly_news_limit": 1},
        now=NOW,
    )

    assert retry.published == 1
    assert retry.rate_limited == 0
    assert sent == ["failed"]
    event = ledger.get(ledger.records()[0].event_id)
    assert event is not None
    assert 701 in event.published_message_ids
