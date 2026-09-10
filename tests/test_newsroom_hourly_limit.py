from datetime import datetime, timedelta, timezone

from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore


BASE = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)


def raw(item_id: str, title: str, *, source: str = "Reuters", minute: int = 0) -> RawNewsItem:
    published = BASE + timedelta(minutes=minute)
    return RawNewsItem(
        source=source,
        source_url=f"https://example.com/{source.lower().replace(' ', '-')}/{item_id}",
        source_item_id=item_id,
        published_at=published.isoformat(),
        fetched_at=(published + timedelta(seconds=5)).isoformat(),
        title=title,
        source_priority="normal",
    )


def stores(tmp_path):
    return (
        EventLedger(tmp_path / "ledger.json"),
        LiveFeedStore(tmp_path / "live.json"),
        LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json"),
    )


def publish_cycle(items, *, ledger, live, editorial, now, sent):
    return run_cycle(
        fetcher=lambda: items,
        ledger=ledger,
        live_feed=live,
        editorial_store=editorial,
        publisher=lambda item: sent.append(item.raw.source_item_id) or {"ok": True, "message_id": 1000 + len(sent)},
        settings={"auto_publish": True, "freshness_hours": 3, "hourly_news_limit": 3},
        now=now,
    )


def seed_three_normal_publications(tmp_path):
    ledger, live, editorial = stores(tmp_path)
    sent = []
    first = [
        raw("sanctions-1", "US imposes new sanctions on Iranian shipping network", minute=1),
        raw("nuclear-1", "IAEA reports new Iran uranium enrichment monitoring figures", minute=2),
        raw("airspace-1", "Iran closes part of its airspace to civilian flights", minute=3),
    ]
    summary = publish_cycle(first, ledger=ledger, live=live, editorial=editorial, now=BASE + timedelta(minutes=10), sent=sent)
    assert summary.published == 3
    assert len(sent) == 3
    return ledger, live, editorial, sent


def test_fourth_normal_unique_story_waits_after_three_news_posts_in_rolling_hour(tmp_path):
    ledger, live, editorial, sent = seed_three_normal_publications(tmp_path)
    item = raw("sanctions-2", "European Union announces additional sanctions on Iranian military suppliers", minute=20)

    summary = publish_cycle([item], ledger=ledger, live=live, editorial=editorial, now=BASE + timedelta(minutes=25), sent=sent)

    assert summary.published == 0
    assert summary.rate_limited == 1
    assert len(sent) == 3
    assert set(sent) == {"sanctions-1", "nuclear-1", "airspace-1"}
    assert "sanctions-2" not in sent
    assert editorial.queue()[-1]["rejection_reason"] == "hourly_publish_limit"
    capped = next(record for record in live.records() if record.item_id == "sanctions-2")
    assert capped.panel_status == "waiting"


def test_distinct_missile_launch_bypasses_hourly_limit(tmp_path):
    ledger, live, editorial, sent = seed_three_normal_publications(tmp_path)
    missile = raw("missile-1", "Iran launches ballistic missiles toward Israel from western Iran", minute=20)

    summary = publish_cycle([missile], ledger=ledger, live=live, editorial=editorial, now=BASE + timedelta(minutes=25), sent=sent)

    assert summary.published == 1
    assert summary.critical_bypasses == 1
    assert sent[-1] == "missile-1"


def test_distinct_explosion_also_bypasses_and_multiple_critical_events_can_exceed_three(tmp_path):
    ledger, live, editorial, sent = seed_three_normal_publications(tmp_path)
    critical = [
        raw("missile-1", "Iran launches ballistic missiles toward Israel from western Iran", minute=20),
        raw("explosion-1", "Large explosion reported at a military site in Tehran", source="AP", minute=21),
    ]

    summary = publish_cycle(critical, ledger=ledger, live=live, editorial=editorial, now=BASE + timedelta(minutes=25), sent=sent)

    assert summary.published == 2
    assert summary.critical_bypasses == 2
    assert sent[-2:] == ["missile-1", "explosion-1"]


def test_same_critical_claim_from_second_source_does_not_use_bypass_twice(tmp_path):
    ledger, live, editorial, sent = seed_three_normal_publications(tmp_path)
    first = raw("missile-r", "Iran launches ballistic missiles toward Israel from western Iran", source="Reuters", minute=20)
    second = raw("missile-ap", "Iran launches ballistic missiles toward Israel from western Iran", source="AP", minute=20)

    one = publish_cycle([first], ledger=ledger, live=live, editorial=editorial, now=BASE + timedelta(minutes=25), sent=sent)
    two = publish_cycle([second], ledger=ledger, live=live, editorial=editorial, now=BASE + timedelta(minutes=26), sent=sent)

    assert one.critical_bypasses == 1
    assert two.critical_bypasses == 0
    assert two.exact_duplicates + two.same_claim_duplicates == 1
    assert sent.count("missile-r") == 1
    assert "missile-ap" not in sent


def test_warning_about_possible_missile_launch_does_not_bypass_limit(tmp_path):
    ledger, live, editorial, sent = seed_three_normal_publications(tmp_path)
    warning = raw("warning-1", "Israel warns Iran could launch ballistic missiles in coming days", minute=20)

    summary = publish_cycle([warning], ledger=ledger, live=live, editorial=editorial, now=BASE + timedelta(minutes=25), sent=sent)

    assert summary.published == 0
    assert summary.critical_bypasses == 0
    assert summary.rate_limited == 1


def test_event_ledger_counts_each_successful_publication_in_rolling_window(tmp_path):
    ledger, _, _, _ = seed_three_normal_publications(tmp_path)
    assert ledger.publication_count_since(BASE - timedelta(minutes=50)) == 3
    assert ledger.publication_count_since(BASE + timedelta(minutes=11)) == 0
