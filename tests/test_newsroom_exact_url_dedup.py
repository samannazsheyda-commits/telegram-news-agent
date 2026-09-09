from datetime import datetime, timezone

from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore


def _raw(item_id: str, fetched_at: str) -> RawNewsItem:
    return RawNewsItem(
        source="Jerusalem Post / X",
        source_url="https://x.com/Jerusalem_Post/status/2097719548220719534",
        source_item_id=item_id,
        published_at="2026-09-09T16:11:00+00:00",
        fetched_at=fetched_at,
        title="Iran missile alert in Israel",
        summary="Israel reports an Iran-related missile alert",
        media=[],
        source_priority="normal",
    )


def test_same_source_url_is_never_published_twice_even_if_item_id_changes(tmp_path):
    now = datetime(2026, 9, 9, 16, 12, tzinfo=timezone.utc)
    ledger = EventLedger(tmp_path / "ledger.json")
    live = LiveFeedStore(tmp_path / "live.json")
    editorial = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")
    calls = []

    def publisher(item):
        calls.append(item.raw.source_item_id)
        return {"ok": True, "message_id": 1000 + len(calls)}

    settings = {"auto_publish": True, "freshness_hours": 2, "panel_max_records": 100}
    run_cycle(lambda: [_raw("first-id", "2026-09-09T16:11:05+00:00")], ledger, live, editorial, publisher, settings, now)
    run_cycle(lambda: [_raw("second-id", "2026-09-09T16:11:15+00:00")], ledger, live, editorial, publisher, settings, now)

    assert calls == ["first-id"]
