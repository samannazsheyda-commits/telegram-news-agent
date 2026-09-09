from __future__ import annotations

from datetime import datetime, timezone

from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore


def test_successful_publish_persists_exact_persian_final_output_for_panel(tmp_path):
    live = LiveFeedStore(tmp_path / "live.json")
    item = RawNewsItem(
        source="Reuters",
        source_url="https://example.com/missile",
        source_item_id="missile-1",
        published_at="2026-09-09T19:20:00+00:00",
        fetched_at="2026-09-09T19:20:10+00:00",
        title="Iran launches missile toward Israel",
        summary="Officials confirmed the launch",
    )
    final = "🚨 <b>رویترز: ایران یک موشک به سمت اسرائیل شلیک کرد</b>\n\nمقام‌ها شلیک را تأیید کردند"
    run_cycle(
        fetcher=lambda: [item],
        ledger=EventLedger(tmp_path / "ledger.json"),
        live_feed=live,
        editorial_store=LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json"),
        publisher=lambda normalized: {
            "ok": True,
            "message_id": 321,
            "persian_title": "ایران یک موشک به سمت اسرائیل شلیک کرد",
            "persian_body": "مقام‌ها شلیک را تأیید کردند",
            "final_message": final,
        },
        settings={"auto_publish": True, "freshness_hours": 3},
        now=datetime(2026, 9, 9, 19, 30, tzinfo=timezone.utc),
    )
    row = live.records()[0]
    assert row.persian_title == "ایران یک موشک به سمت اسرائیل شلیک کرد"
    assert row.persian_body == "مقام‌ها شلیک را تأیید کردند"
    assert row.final_message == final
    assert row.original_summary == "Officials confirmed the launch"


def test_filtered_item_exposes_no_english_as_panel_display_title(tmp_path):
    live = LiveFeedStore(tmp_path / "live.json")
    item = RawNewsItem(
        source="Reuters",
        source_url="https://example.com/politics",
        source_item_id="politics-1",
        published_at="2026-09-09T19:20:00+00:00",
        fetched_at="2026-09-09T19:20:10+00:00",
        title="Iran president meets parliament leaders",
    )
    run_cycle(
        fetcher=lambda: [item],
        ledger=EventLedger(tmp_path / "ledger.json"),
        live_feed=live,
        editorial_store=LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json"),
        publisher=lambda normalized: (_ for _ in ()).throw(AssertionError("must not publish")),
        settings={"auto_publish": True, "freshness_hours": 3},
        now=datetime(2026, 9, 9, 19, 30, tzinfo=timezone.utc),
    )
    row = live.records()[0]
    assert row.persian_title == "خارج از حوزه خبری بی‌خبر"
