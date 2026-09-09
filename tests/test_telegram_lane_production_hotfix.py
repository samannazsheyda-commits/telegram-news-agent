from datetime import datetime, timezone

from src import realtime_direct_sources as direct
from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore
from src.sources import NewsItem


def test_priority_telegram_uses_managed_rows_even_without_custom_file(monkeypatch, tmp_path):
    monkeypatch.setattr(
        direct,
        "managed_source_rows",
        lambda custom_path=None: [
            {
                "id": "tabzlive-telegram",
                "kind": "telegram",
                "name": "Tabz Live",
                "channel": "tabzlive",
                "active": True,
                "status": "realtime",
                "system": True,
            }
        ],
    )
    monkeypatch.setattr(
        direct,
        "_fetch_telegram_source",
        lambda source, session=None: [
            NewsItem(
                "tg-1",
                "Tabz Live / Telegram",
                "Iran launches missile",
                "Iran launches missile",
                "https://t.me/tabzlive/1",
                "Wed, 09 Sep 2026 12:00:00 +0000",
            )
        ],
    )
    items = direct.fetch_priority_telegram_realtime(path=tmp_path / "missing.json")
    assert len(items) == 1
    assert items[0].source == "Tabz Live / Telegram"


def test_publisher_exception_is_visible_in_logs(tmp_path, capsys):
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    raw = RawNewsItem(
        source="Test / Telegram",
        source_url="https://t.me/test/1",
        source_item_id="1",
        published_at="Wed, 09 Sep 2026 12:00:00 +0000",
        fetched_at=now.isoformat(),
        title="Iran missile attack reported",
        summary="Iran missile attack reported",
        source_priority="protected",
    )
    ledger = EventLedger(tmp_path / "ledger.json")
    feed = LiveFeedStore(tmp_path / "feed.json")
    editorial = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")

    def boom(_item):
        raise RuntimeError("publisher exploded")

    summary = run_cycle(
        lambda: [raw],
        ledger,
        feed,
        editorial,
        boom,
        {"auto_publish": True, "freshness_hours": 2},
        now,
    )
    assert summary.publish_failed == 1
    assert "PUBLISH_EXCEPTION" in capsys.readouterr().out
