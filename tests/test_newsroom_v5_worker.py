from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.newsroom_v5_events import SqliteEventLog
from src.newsroom_v5_pipeline import NewsroomV5Pipeline
from src.newsroom_v5_publish import AmbiguousPublishError, prepare_publication, process_publication
from src.newsroom_v5_store import NewsroomV5Store
from src.newsroom_v5_worker import NewsroomV5Worker, format_telegram_message


FA = {
    "Missiles launched at the port": "موشک‌ها به سمت بندر شلیک شدند",
    "Details from the port": "جزئیات از بندر",
    "Officials met again": "مقام‌ها دوباره دیدار کردند",
}


def translator(text: str) -> str:
    return FA.get(text, "")


def _fresh() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()


def _ingest(store, story_id="s1", title="Missiles launched at the port", published=None, source="reuters"):
    pipeline = NewsroomV5Pipeline(store, lightweight_translator=translator)
    return pipeline.ingest({
        "id": story_id,
        "source_item_id": story_id,
        "source_id": source,
        "source_name": source,
        "source_url": f"https://example.test/{story_id}",
        "original_title": title,
        "original_body": "Details from the port",
        "published_at_source": published or _fresh(),
    })


def _make_available(store):
    store.conn.execute("UPDATE jobs SET available_at='2000-01-01T00:00:00+00:00' WHERE status='pending'")


CRITICAL = {"priority_class": "critical", "importance": 95, "publish": True, "new_fact": True, "reason": "attack"}


@pytest.fixture
def store(tmp_path):
    s = NewsroomV5Store(tmp_path / "v5.db")
    s.upsert_source({"id": "reuters", "name": "Reuters", "enabled": True})
    yield s
    s.close()


def _worker(store, **kwargs):
    kwargs.setdefault("lightweight_translator", translator)
    kwargs.setdefault("events", SqliteEventLog(store))
    return NewsroomV5Worker(store, worker_id="test", **kwargs)


def test_english_story_is_translated_then_routed_to_review_with_live_event(store):
    _ingest(store)
    assert store.list_review()["items"] == []

    summary = _worker(store).run_once()

    assert summary["translated"] == 1 and summary["review"] == 1
    items = store.list_review()["items"]
    assert [row["id"] for row in items] == ["s1"]
    assert items[0]["title_fa"] == FA["Missiles launched at the port"]
    types = [e.type for e in SqliteEventLog(store).events_after(0)]
    assert "story_added" in types and "counts_changed" in types


def test_failed_translation_is_retried_with_backoff_not_lost(store):
    _ingest(store)
    failing = _worker(store, lightweight_translator=lambda _t: "")
    failing.run_once()

    story = store.get_story("s1")
    assert story["state"] == "received"
    job = dict(store.conn.execute("SELECT * FROM jobs WHERE kind='translate_story'").fetchone())
    assert job["status"] == "pending", "a failed translation must stay scheduled, not be marked done"
    assert job["attempt_count"] == 1
    assert job["available_at"] > datetime.now(timezone.utc).isoformat()
    assert store.list_review()["items"] == []

    _make_available(store)
    _worker(store).run_once()
    assert store.get_story("s1")["state"] == "review"


def test_editorial_model_outage_still_routes_relevant_story_to_review(store):
    _ingest(store)

    def broken(_story):
        raise RuntimeError("model down")

    _worker(store, decide=broken).run_once()
    assert store.get_story("s1")["state"] == "review"
    audit = [row[0] for row in store.conn.execute("SELECT action FROM audit_log")]
    assert "editorial_model_failed" in audit


def test_duplicate_and_irrelevant_decisions_stay_out_of_review(store):
    _ingest(store, "dup")
    _ingest(store, "off", title="Officials met again")
    decisions = {"dup": {"duplicate": True}, "off": {"relevant": False}}
    _worker(store, decide=lambda story: decisions[story["id"]]).run_once()
    assert store.get_story("dup")["state"] == "duplicate"
    assert store.get_story("off")["state"] == "irrelevant"
    assert store.list_review()["items"] == []


def test_auto_publish_disabled_routes_critical_story_to_review(store):
    _ingest(store)
    sent = []
    _worker(store, decide=lambda _s: CRITICAL, sender=lambda t, b: sent.append(t) or 1,
            auto_publish_enabled=False).run_once()
    assert store.get_story("s1")["state"] == "review"
    assert sent == []


def test_auto_publish_enabled_publishes_critical_story_exactly_once(store):
    _ingest(store)
    sent = []
    worker = _worker(store, decide=lambda _s: CRITICAL, sender=lambda t, b: sent.append(t) or 4242,
                     auto_publish_enabled=True)
    worker.run_once()
    worker.run_once()
    assert store.get_story("s1")["state"] == "published"
    assert len(sent) == 1
    assert "story_published" in [e.type for e in SqliteEventLog(store).events_after(0)]


def test_auto_candidate_without_telegram_sender_lands_in_review(store):
    _ingest(store)
    _worker(store, decide=lambda _s: CRITICAL, sender=None, auto_publish_enabled=True).run_once()
    assert store.get_story("s1")["state"] == "review"


def test_stale_or_disabled_source_story_never_auto_publishes(store):
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    _ingest(store, "old", published=old)
    store.upsert_source({"id": "muted", "name": "Muted", "enabled": False})
    _ingest(store, "muted-story", source="muted")
    sent = []
    _worker(store, decide=lambda _s: CRITICAL, sender=lambda t, b: sent.append(t) or 1,
            auto_publish_enabled=True).run_once()
    assert store.get_story("old")["state"] == "review"
    assert store.get_story("muted-story")["state"] == "review"
    assert sent == []


def test_anti_flood_pacing_routes_burst_to_review_instead_of_dropping(store):
    _ingest(store, "a")
    _ingest(store, "b")
    sent = []
    _worker(store, decide=lambda _s: CRITICAL, sender=lambda t, b: sent.append(t) or len(sent),
            auto_publish_enabled=True, min_publish_interval_seconds=600).run_once()
    states = sorted(store.get_story(i)["state"] for i in ("a", "b"))
    assert states == ["published", "review"]
    assert len(sent) == 1
    reasons = [row[0] for row in store.conn.execute(
        "SELECT detail_json FROM audit_log WHERE action='auto_publish_deferred'")]
    assert any("anti_flood_pacing" in reason for reason in reasons)


def _review_story(store, story_id="p1"):
    store.upsert_story({"id": story_id, "news_key": story_id, "source_id": "reuters", "source_name": "Reuters",
                        "source_url": f"https://example.test/{story_id}", "original_title": "x",
                        "published_at_source": _fresh(), "state": "review"})
    store.set_translation(story_id, title_fa="تیتر خبر", body_fa="متن", backend="t", quality_passed=True)


def test_operator_publish_job_is_not_claimed_without_telegram_writes(store):
    _review_story(store)
    prepare_publication(store, "p1", idempotency_key="k1")
    _worker(store, sender=None).run_once()
    job = store.conn.execute("SELECT status FROM jobs WHERE kind='publish_story'").fetchone()
    assert job[0] == "pending"
    assert store.get_story("p1")["state"] == "publishing"


def test_publish_hard_failure_keeps_job_scheduled_then_sends(store):
    _review_story(store)
    prepare_publication(store, "p1", idempotency_key="k1")
    calls = {"n": 0}

    def flaky(_t, _b):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("telegram 502")
        return 77

    worker = _worker(store, sender=flaky)
    worker.run_once()
    assert store.conn.execute("SELECT status FROM jobs WHERE kind='publish_story'").fetchone()[0] == "pending"
    _make_available(store)
    worker.run_once()
    assert store.get_story("p1")["state"] == "published"
    assert calls["n"] == 2


def test_reconcile_without_reconciler_never_resends(store):
    _review_story(store)
    publication = prepare_publication(store, "p1", idempotency_key="k1")
    store.update_publication(publication["id"], status="reconcile")
    sent = []
    result = process_publication(store, publication["id"], sender=lambda t, b: sent.append(t) or 1)
    assert sent == []
    assert result["status"] == "reconcile"


def test_ambiguous_timeout_then_confirmed_absent_resends_once(store):
    _review_story(store)
    publication = prepare_publication(store, "p1", idempotency_key="k1")
    calls = {"n": 0}

    def sender(_t, _b):
        calls["n"] += 1
        if calls["n"] == 1:
            raise AmbiguousPublishError("read timeout")
        return 99

    worker = _worker(store, sender=sender, reconciler=lambda pub: {"found": False, "confirmed_absent": True})
    worker.run_once()
    assert calls["n"] == 1
    assert store.get_publication(publication["id"])["status"] == "retry"
    assert store.get_story("p1")["state"] == "publishing"
    worker.run_once()
    worker.run_once()
    assert store.get_story("p1")["state"] == "published"
    assert calls["n"] == 2


class _Session:
    def __init__(self, exc=None, message_id=5):
        self.exc, self.message_id, self.calls = exc, message_id, 0

    def post(self, *_a, **_k):
        self.calls += 1
        if self.exc:
            raise self.exc

        class R:
            def raise_for_status(_self):
                return None

            def json(_self):
                return {"ok": True, "result": {"message_id": self.message_id}}
        return R()


def test_telegram_sender_classifies_lost_response_as_ambiguous():
    import requests
    from src.newsroom_v5_worker import telegram_message_sender

    assert telegram_message_sender("t", "c", session=_Session(message_id=12))("x") == 12
    with pytest.raises(AmbiguousPublishError):
        telegram_message_sender("t", "c", session=_Session(requests.ReadTimeout()))("x")
    with pytest.raises(requests.ConnectTimeout):
        telegram_message_sender("t", "c", session=_Session(requests.ConnectTimeout()))("x")


def test_worker_env_keeps_telegram_writes_off_in_shadow_mode(store, monkeypatch):
    from src.newsroom_v5_worker import build_worker_from_env

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setenv("NEWSROOM_V5_TELEGRAM_WRITES_ENABLED", "true")
    monkeypatch.setenv("NEWSROOM_V5_SHADOW_PIPELINE", "true")
    monkeypatch.setenv("NEWSROOM_AUTO_PUBLISH_ENABLED", "true")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    worker = build_worker_from_env(store)
    assert worker.telegram_writes is False
    assert worker.auto_publish_enabled is False

    monkeypatch.delenv("NEWSROOM_V5_SHADOW_PIPELINE")
    monkeypatch.delenv("NEWSROOM_AUTO_PUBLISH_ENABLED")
    worker = build_worker_from_env(store)
    assert worker.telegram_writes is True
    assert worker.auto_publish_enabled is False


def test_telegram_message_uses_channel_format():
    text = format_telegram_message({
        "source_name": "Reuters", "source_url": "https://example.test/a", "news_key": "a",
        "original_title": "x", "original_body": "", "published_at_source": "2026-09-20T10:00:00+00:00",
    }, "تیتر خبر", "")
    assert "<b>رویترز: تیتر خبر.</b>" in text
    assert 'href="https://example.test/a"' in text
