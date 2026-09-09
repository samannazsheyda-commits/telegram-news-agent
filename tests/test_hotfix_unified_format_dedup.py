from datetime import datetime, timezone

from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.final_output import finalize_telegram_message
from src.newsroom_decision import decide_item
from src.newsroom_fingerprint import build_fingerprint
from src.newsroom_models import EventRecord, RawNewsItem
from src.newsroom_normalize import normalize_item
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore
from src.urgent_output import normalize_urgent_message


NOW = datetime(2026, 9, 9, 21, 30, tzinfo=timezone.utc)


def _raw(source, item_id, title, *, url, published="2026-09-09T21:22:00+00:00"):
    return RawNewsItem(
        source=source,
        source_url=url,
        source_item_id=item_id,
        published_at=published,
        fetched_at="2026-09-09T21:23:00+00:00",
        title=title,
        source_priority="normal",
    )


def test_every_breaking_path_uses_one_final_formatter_guard():
    legacy = (
        '💥 🔴 <b>خبر فوری</b>\n'
        '🛑 <b>RN Intel / Telegram: 🇮🇷 ⚡️ - گزارش های اولیه از وقوع انفجار در نقاط مختلف سواحل جنوب ایران.</b>\n'
        '⏰ ۱۹ شهریور ۱۴۰۵ — ۰۰:۵۳\n'
        '📌 <a href="https://t.me/rnintel/66307">لینک منبع خبر</a>\n'
        '📡 <a href="https://t.me/bikhabaar">بی‌خبر</a> ←\n'
        'مانیتور تحولات ایران'
    )
    final = finalize_telegram_message(legacy)
    assert final == normalize_urgent_message(legacy)
    assert "RN Intel" not in final
    assert "Telegram" not in final
    assert "🇮🇷" not in final
    assert "آر‌اِن اینتل / تلگرام" in final
    assert final.startswith("💥 🔴 <b>خبر فوری | آر‌اِن اینتل / تلگرام:")
    assert "\n\n⏰ " in final
    assert "\n📌 " in final
    assert "\n\n📡 " in final


def test_sparse_identical_fingerprint_is_same_claim_duplicate():
    prior_raw = _raw(
        "US State Department / X",
        "prior-quote",
        "Trump says Iran talks involve far more than a nuclear agreement",
        url="https://x.com/state/status/1",
        published="2026-09-09T18:00:00+00:00",
    )
    current_raw = _raw(
        "US State Department / X",
        "current-quote",
        "Trump says Iran talks involve far more than a nuclear agreement",
        url="https://x.com/state/status/2",
        published="2026-09-09T20:30:00+00:00",
    )
    prior_item = normalize_item(prior_raw)
    current_item = normalize_item(current_raw)
    prior_fp = build_fingerprint(prior_item)
    current_fp = build_fingerprint(current_item)
    assert prior_fp.key == current_fp.key
    prior = EventRecord(
        event_id="event-prior",
        fingerprint=prior_fp.key,
        canonical_title=prior_raw.title,
        first_seen=prior_raw.fetched_at,
        last_updated=prior_raw.fetched_at,
        primary_source=prior_raw.source,
        source_variants=[prior_raw.source_url],
        key_facts=list(prior_fp.key_facts),
        published_message_ids=[1001],
        status="published",
        fingerprint_data={
            "actors": list(prior_fp.actors),
            "actions": list(prior_fp.actions),
            "objects": list(prior_fp.objects),
            "locations": list(prior_fp.locations),
            "key_facts": list(prior_fp.key_facts),
            "time_bucket": prior_fp.time_bucket,
            "source_item_id": prior_raw.source_item_id,
        },
    )
    result = decide_item(current_item, current_fp, [prior])
    assert result.decision == "duplicate_same_claim"
    assert result.duplicate_of == "event-prior"


def test_cross_source_same_explosion_alert_publishes_once(tmp_path):
    items = [
        _raw(
            "Tabz Live / Telegram",
            "102649",
            "Initial reports of an explosion in Qeshm in southern Iran; nature of the sound is unknown",
            url="https://t.me/tabzlive/102649",
        ),
        _raw(
            "RN Intel / Telegram",
            "66307",
            "Initial reports of explosions on Iran's southern coast including Qeshm",
            url="https://t.me/rnintel/66307",
            published="2026-09-09T21:23:00+00:00",
        ),
    ]
    sent = []
    summary = run_cycle(
        fetcher=lambda: items,
        ledger=EventLedger(tmp_path / "ledger.json"),
        live_feed=LiveFeedStore(tmp_path / "live.json"),
        editorial_store=LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json"),
        publisher=lambda item: sent.append(item.raw.source_item_id) or {"ok": True, "message_id": 700 + len(sent)},
        settings={"auto_publish": True, "freshness_hours": 3},
        now=NOW,
    )
    assert summary.published == 1
    assert summary.same_claim_duplicates == 1
    assert len(sent) == 1


def test_distinct_explosion_locations_are_not_collapsed(tmp_path):
    items = [
        _raw(
            "Tabz Live / Telegram",
            "qeshm",
            "Explosion reported in Qeshm in southern Iran",
            url="https://t.me/tabzlive/200001",
        ),
        _raw(
            "RN Intel / Telegram",
            "bushehr",
            "Explosion reported in Bushehr in southern Iran",
            url="https://t.me/rnintel/200002",
            published="2026-09-09T21:23:00+00:00",
        ),
    ]
    sent = []
    summary = run_cycle(
        fetcher=lambda: items,
        ledger=EventLedger(tmp_path / "ledger.json"),
        live_feed=LiveFeedStore(tmp_path / "live.json"),
        editorial_store=LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json"),
        publisher=lambda item: sent.append(item.raw.source_item_id) or {"ok": True, "message_id": 800 + len(sent)},
        settings={"auto_publish": True, "freshness_hours": 3},
        now=NOW,
    )
    assert summary.published == 2
    assert len(sent) == 2


def test_event_ledger_persists_source_item_id(tmp_path):
    item = normalize_item(
        _raw(
            "RN Intel / Telegram",
            "66307",
            "Initial reports of an explosion in Qeshm in southern Iran",
            url="https://t.me/rnintel/66307",
        )
    )
    fp = build_fingerprint(item)
    ledger = EventLedger(tmp_path / "ledger.json")
    event = ledger.create_event(
        fingerprint=fp,
        canonical_title=item.raw.title,
        primary_source=item.raw.source,
        source_url=item.raw.source_url,
        source_item_id=item.raw.source_item_id,
        first_seen=item.raw.fetched_at,
        key_facts=fp.key_facts,
    )
    assert event.fingerprint_data["source_item_id"] == "66307"
    assert ledger.records()[0].fingerprint_data["source_item_id"] == "66307"
