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


def test_stale_story_is_dropped_before_realtime_state_and_never_published(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    sent = []
    summary = run_cycle(
        lambda: [item("old", "Iran announces tanker restrictions in Strait of Hormuz", "2026-09-05T12:00:00+00:00")],
        ledger, live, editorial,
        lambda x: sent.append(x) or {"ok": True, "message_id": 1},
        {"auto_publish": True}, NOW,
    )
    assert sent == []
    assert summary.stale == 1
    assert live.records() == []
    assert ledger.records() == []


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
    assert live.records()[0].decision_reason == "filtered_outside_channel_scope"


def test_protected_ambiguous_story_is_hard_filtered_not_reviewed(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    sent = []
    summary = run_cycle(
        lambda: [item("protected", "White House issues a new statement about Iran", "2026-09-07T21:00:00+00:00", source="White House", priority="protected")],
        ledger, live, editorial,
        lambda x: sent.append(x) or {"ok": True, "message_id": 3},
        {"auto_publish": True}, NOW,
    )
    assert sent == []
    assert summary.review_items == 0
    assert editorial.queue() == []
    assert live.records()[0].panel_status == "rejected"
    assert live.records()[0].decision_reason == "filtered_outside_channel_scope"


def test_fresh_in_scope_iran_story_reaches_publisher(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    sent = []
    summary = run_cycle(
        lambda: [item("fresh", "Iran launches ballistic missiles toward Israel", "2026-09-07T21:00:00+00:00")],
        ledger, live, editorial,
        lambda x: sent.append(x.raw.source_item_id) or {"ok": True, "message_id": 44},
        {"auto_publish": True}, NOW,
    )
    assert sent == ["fresh"]
    assert summary.published == 1
