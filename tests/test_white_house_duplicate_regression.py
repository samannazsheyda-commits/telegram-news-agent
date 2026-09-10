from datetime import datetime, timezone

from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore


def _white_house(item_id: str, published_at: str, title: str) -> RawNewsItem:
    return RawNewsItem(
        source="White House / X",
        source_url=f"https://x.com/WhiteHouse/status/{item_id}",
        source_item_id=item_id,
        published_at=published_at,
        fetched_at=published_at,
        title=title,
        summary="The White House repeated the same warning concerning Iranian missile attacks.",
        source_priority="protected",
    )


def test_same_white_house_claim_two_hours_apart_publishes_only_once(tmp_path):
    older = _white_house(
        "1001",
        "2026-09-10T16:00:00+00:00",
        "White House says President Trump demands Iran halt missile attacks on Israel immediately",
    )
    newer = _white_house(
        "1002",
        "2026-09-10T18:00:00+00:00",
        "White House: Trump demands Iran immediately halt its missile attacks against Israel",
    )
    sent = []
    summary = run_cycle(
        lambda: [older, newer],
        EventLedger(tmp_path / "ledger.json"),
        LiveFeedStore(tmp_path / "live.json"),
        LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json"),
        lambda item: sent.append(item) or {"ok": True, "message_id": 9000 + len(sent)},
        {"auto_publish": True, "freshness_hours": 6},
        datetime(2026, 9, 10, 18, 10, tzinfo=timezone.utc),
    )
    assert summary.published == 1
    assert len(sent) == 1
    assert summary.same_claim_duplicates == 1
