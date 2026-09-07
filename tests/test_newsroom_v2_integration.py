from datetime import datetime, timezone

from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore


NOW = datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc)


def raw(source, item_id, title, *, priority="normal", url=None):
    return RawNewsItem(
        source=source,
        source_url=url or f"https://example.com/{item_id}",
        source_item_id=item_id,
        published_at="2026-09-07T12:00:00+00:00",
        fetched_at="2026-09-07T12:01:00+00:00",
        title=title,
        source_priority=priority,
    )


def stores(tmp_path):
    return (
        EventLedger(tmp_path / "ledger.json"),
        LiveFeedStore(tmp_path / "live.json"),
        LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json"),
    )


def test_cycle_keeps_independent_hormuz_events_and_dedupes_true_duplicate(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    items = [
        raw("White House", "wh-1", "White House says United States has total control of Strait of Hormuz", priority="protected"),
        raw("Reuters", "r-zone", "Iran announces new restricted zone outside Strait of Hormuz"),
        raw("CENTCOM", "c-92", "CENTCOM redirected 92 commercial vessels, disabled 3 and boarded 2 in Strait of Hormuz", priority="protected"),
        raw("Reuters", "tank-r", "U.S. military struck three Iranian oil tankers after attacks on Navy warships"),
        raw("AP", "tank-ap", "US forces strike 3 Iranian crude oil tankers after Iran targets Navy ships"),
    ]

    sent = []
    summary = run_cycle(
        fetcher=lambda: items,
        ledger=ledger,
        live_feed=live,
        editorial_store=editorial,
        publisher=lambda item: sent.append(item.raw.source_item_id) or {"ok": True, "message_id": 700 + len(sent)},
        settings={"auto_publish": True, "freshness_hours": 3},
        now=NOW,
    )

    assert summary.items_fetched == 5
    assert summary.new_events == 4
    assert summary.exact_duplicates + summary.same_claim_duplicates == 1
    assert len(live.records()) == 5
    assert len(sent) == 4


def test_auto_publish_true_still_populates_live_feed(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    summary = run_cycle(
        fetcher=lambda: [raw("Reuters", "one", "Iran partially reopens airspace to international flights")],
        ledger=ledger,
        live_feed=live,
        editorial_store=editorial,
        publisher=lambda item: {"ok": True, "message_id": 777},
        settings={"auto_publish": True},
        now=NOW,
    )
    assert summary.panel_feed_count == 1
    assert len(live.records()) == 1
    assert live.records()[0].panel_status == "auto_published"
    assert editorial.queue() == []


def test_auto_publish_off_queues_item_and_live_feed_remains_visible(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    summary = run_cycle(
        fetcher=lambda: [raw("Reuters", "manual", "Jordan intercepts Iranian missiles over its airspace")],
        ledger=ledger,
        live_feed=live,
        editorial_store=editorial,
        publisher=lambda item: (_ for _ in ()).throw(AssertionError("publisher must not run")),
        settings={"auto_publish": False},
        now=NOW,
    )
    assert summary.review_items == 1
    assert len(editorial.queue()) == 1
    assert live.records()[0].panel_status == "waiting"


def test_one_source_failure_does_not_abort_other_sources(tmp_path):
    ledger, live, editorial = stores(tmp_path)

    def broken():
        raise RuntimeError("source down")

    def healthy():
        return [raw("Reuters", "healthy", "Iran announces new restricted zone in Gulf")]

    summary = run_cycle(
        fetcher=[broken, healthy],
        ledger=ledger,
        live_feed=live,
        editorial_store=editorial,
        publisher=lambda item: {"ok": True, "message_id": 888},
        settings={"auto_publish": True},
        now=NOW,
    )
    assert summary.sources_failed == 1
    assert summary.sources_ok == 1
    assert summary.items_fetched == 1
    assert len(live.records()) == 1


def test_shadow_mode_never_publishes_but_records_decisions(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    summary = run_cycle(
        fetcher=lambda: [raw("Reuters", "shadow", "Spain closes airspace to US warplanes involved in Iran war")],
        ledger=ledger,
        live_feed=live,
        editorial_store=editorial,
        publisher=lambda item: (_ for _ in ()).throw(AssertionError("shadow must not publish")),
        settings={"auto_publish": True},
        now=NOW,
        shadow=True,
    )
    assert summary.new_events == 1
    assert len(live.records()) == 1
    assert live.records()[0].panel_status == "new"
