from __future__ import annotations

from src.newsroom_v5_publish import AmbiguousPublishError, prepare_publication, process_publication
from src.newsroom_v5_store import NewsroomV5Store


def _publication(store):
    store.upsert_story({
        "id": "s1", "news_key": "s1", "source_id": "src", "source_name": "Source",
        "source_url": "https://example.test/s1", "source_item_id": "s1",
        "original_title": "Original", "published_at_source": "2026-09-20T10:00:00+00:00", "state": "review",
    })
    store.set_translation("s1", title_fa="تیتر", body_fa="متن", backend="test", quality_passed=True)
    return prepare_publication(store, "s1", idempotency_key="publish:s1")


def test_success_records_message_id_and_publishes_story(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    publication = _publication(store)
    result = process_publication(store, publication["id"], sender=lambda title, body: 777)
    assert result["status"] == "published"
    assert result["telegram_message_id"] == "777"
    assert store.get_story("s1")["state"] == "published"


def test_hard_failure_schedules_retry_without_losing_story(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    publication = _publication(store)

    def fail(*_):
        raise RuntimeError("telegram unavailable")

    result = process_publication(store, publication["id"], sender=fail)
    assert result["status"] == "retry"
    assert store.get_story("s1")["state"] == "publishing"
    assert store.conn.execute("SELECT COUNT(*) FROM jobs WHERE kind='publish_story' AND status='pending'").fetchone()[0] >= 1


def test_ambiguous_timeout_schedules_reconciliation_not_blind_resend(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    publication = _publication(store)
    calls = {"send": 0}

    def ambiguous(*_):
        calls["send"] += 1
        raise AmbiguousPublishError("timeout after submit")

    result = process_publication(store, publication["id"], sender=ambiguous)
    assert result["status"] == "reconcile"
    assert calls["send"] == 1
    assert store.conn.execute("SELECT COUNT(*) FROM jobs WHERE kind='reconcile_publication'").fetchone()[0] == 1


def test_reconciled_success_does_not_send_again(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    publication = _publication(store)
    store.update_publication(publication["id"], status="reconcile")
    calls = {"send": 0}

    def sender(*_):
        calls["send"] += 1
        return 999

    result = process_publication(
        store,
        publication["id"],
        sender=sender,
        reconciler=lambda pub: {"found": True, "telegram_message_id": 888},
    )
    assert result["status"] == "published"
    assert result["telegram_message_id"] == "888"
    assert calls["send"] == 0
