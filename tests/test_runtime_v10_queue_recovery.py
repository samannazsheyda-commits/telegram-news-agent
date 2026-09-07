from datetime import datetime, timedelta, timezone

from src import runtime_v10 as v10


def _record(key: str, published: datetime, **overrides):
    record = {
        "news_key": key,
        "source": "کلش ریپورت / Telegram",
        "source_url": f"https://t.me/example/{key}",
        "original_title": "Iran's Security Council Secretary Rezaei: We tested an anti-ship missile above an American warship.",
        "original_summary": "Iran's Security Council Secretary Rezaei: We tested an anti-ship missile above an American warship.",
        "published_at_source": published.strftime("%a, %d %b %Y %H:%M:%S +0000"),
        "rejection_reason": "bundled_or_multi_headline",
        "status": "pending",
    }
    record.update(overrides)
    return record


def test_queue_recovery_injects_recent_false_bundle_even_when_source_feed_no_longer_has_it(monkeypatch):
    now = datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(v10.base._store, "queue", lambda: [_record("stuck", now - timedelta(hours=11))])
    monkeypatch.setattr(v10, "_original_combined_fetch", lambda: [])

    items = v10._combined_fetch_with_queue_recovery(now=now)

    assert [item.key for item in items] == ["stuck"]


def test_queue_recovery_skips_old_or_non_pending_records(monkeypatch):
    now = datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc)
    records = [
        _record("old", now - timedelta(hours=25)),
        _record("done", now - timedelta(hours=5), status="published_auto"),
        _record("other-reason", now - timedelta(hours=5), rejection_reason="duplicate_or_redundant"),
    ]
    monkeypatch.setattr(v10.base._store, "queue", lambda: records)
    monkeypatch.setattr(v10, "_original_combined_fetch", lambda: [])

    assert v10._combined_fetch_with_queue_recovery(now=now) == []
