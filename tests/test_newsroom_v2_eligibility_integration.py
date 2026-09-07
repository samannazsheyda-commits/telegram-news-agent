from datetime import datetime, timezone

from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore

NOW = datetime(2026, 9, 7, 21, 30, tzinfo=timezone.utc)


def item(item_id, title, published_at, *, source="Reuters", priority="normal", summary=""):
    return RawNewsItem(
        source=source,
        source_url=f"https://example.com/{item_id}",
        source_item_id=item_id,
        published_at=published_at,
        fetched_at=NOW.isoformat(),
        title=title,
        summary=summary,
        source_priority=priority,
    )


def stores(tmp_path):
    return EventLedger(tmp_path / "ledger.json"), LiveFeedStore(tmp_path / "live.json"), LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")


def test_stale_story_is_visible_but_never_published(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    sent = []
    summary = run_cycle(
        lambda: [item("old", "Iran announces maritime restrictions", "2026-09-05T12:00:00+00:00")],
        ledger, live, editorial,
        lambda x: sent.append(x) or {"ok": True, "message_id": 1},
        {"auto_publish": True}, NOW,
    )
    assert sent == []
    assert summary.stale == 1
    assert live.records()[0].panel_status == "rejected"
    assert live.records()[0].decision_reason == "stale"


def test_low_value_company_story_is_visible_but_never_published(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    sent = []
    summary = run_cycle(
        lambda: [item("biz", "Company reports quarterly profit growth in Iran market", "2026-09-07T21:00:00+00:00", summary="Revenue and sales increased")],
        ledger, live, editorial,
        lambda x: sent.append(x) or {"ok": True, "message_id": 2},
        {"auto_publish": True}, NOW,
    )
    assert sent == []
    assert summary.filtered == 1
    assert live.records()[0].decision_reason == "filtered_low_value"


def test_protected_ambiguous_story_enters_review_not_publish(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    sent = []
    summary = run_cycle(
        lambda: [item("protected", "White House issues a new statement", "2026-09-07T21:00:00+00:00", source="White House", priority="protected")],
        ledger, live, editorial,
        lambda x: sent.append(x) or {"ok": True, "message_id": 3},
        {"auto_publish": True}, NOW,
    )
    assert sent == []
    assert summary.review_items == 1
    assert len(editorial.queue()) == 1
    assert live.records()[0].panel_status == "waiting"


def test_fresh_operational_iran_story_reaches_publisher(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    sent = []
    summary = run_cycle(
        lambda: [item("fresh", "Iran partially reopens airspace after security restrictions", "2026-09-07T21:00:00+00:00")],
        ledger, live, editorial,
        lambda x: sent.append(x.raw.source_item_id) or {"ok": True, "message_id": 44},
        {"auto_publish": True}, NOW,
    )
    assert sent == ["fresh"]
    assert summary.published == 1
