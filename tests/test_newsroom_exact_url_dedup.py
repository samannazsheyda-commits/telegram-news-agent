from datetime import datetime, timezone

from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore


URL = "https://x.com/Jerusalem_Post/status/2097719548220719534"


def _raw(item_id: str, fetched_at: str, *, title: str, summary: str) -> RawNewsItem:
    return RawNewsItem(
        source="Jerusalem Post / X",
        source_url=URL,
        source_item_id=item_id,
        published_at="2026-09-09T16:11:00+00:00",
        fetched_at=fetched_at,
        title=title,
        summary=summary,
        media=[],
        source_priority="normal",
    )


def test_same_source_url_is_never_published_twice_even_if_item_id_and_text_change(tmp_path):
    now = datetime(2026, 9, 9, 16, 12, tzinfo=timezone.utc)
    ledger = EventLedger(tmp_path / "ledger.json")
    live = LiveFeedStore(tmp_path / "live.json")
    editorial = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")
    calls = []

    def publisher(item):
        calls.append(item.raw.source_item_id)
        return {
            "ok": True,
            "message_id": 1000 + len(calls),
            "persian_title": "هشدار موشکی ایران در اسرائیل",
            "persian_body": "اسرائیل از هشدار مرتبط با موشک ایران خبر داد.",
            "final_message": "🛑 جروزالم پست / ایکس: هشدار موشکی ایران در اسرائیل",
        }

    settings = {"auto_publish": True, "freshness_hours": 2, "panel_max_records": 100}
    first = _raw(
        "first-id",
        "2026-09-09T16:11:05+00:00",
        title="Iran missile alert in Israel",
        summary="Israel reports an Iran-related missile alert",
    )
    mutated_same_post = _raw(
        "second-id",
        "2026-09-09T16:11:15+00:00",
        title="Former Mossad official discusses defeating Iran under a different Israeli government",
        summary="A former official gave a political assessment involving Iran and an Israeli political party",
    )

    run_cycle(lambda: [first], ledger, live, editorial, publisher, settings, now)
    row = live.records()[0]
    assert row.persian_title == "هشدار موشکی ایران در اسرائیل"
    assert row.persian_body == "اسرائیل از هشدار مرتبط با موشک ایران خبر داد."
    assert row.final_message.startswith("🛑 جروزالم پست / ایکس")

    run_cycle(lambda: [mutated_same_post], ledger, live, editorial, publisher, settings, now)
    assert calls == ["first-id"]
