from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.ai_newsroom import AIServiceError, EditorialDecision, RelationDecision
from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_fingerprint import build_fingerprint
from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore


NOW = datetime.fromisoformat("2026-09-11T10:00:00+00:00")


def _raw(title, *, source="Reuters", url="https://example.com/new", item_id="new", summary="", published=None, priority="normal"):
    return RawNewsItem(
        source=source,
        source_url=url,
        source_item_id=item_id,
        published_at=(published or (NOW - timedelta(minutes=5))).isoformat(),
        fetched_at=NOW.isoformat(),
        title=title,
        summary=summary,
        source_priority=priority,
    )


def _stores(tmp_path):
    ledger = EventLedger(tmp_path / "events.json")
    feed = LiveFeedStore(tmp_path / "feed.json")
    editorial = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")
    return ledger, feed, editorial


def _seed_published(ledger, raw, *, seen_at=None):
    item = normalize_item(raw)
    fp = build_fingerprint(item)
    seen = (seen_at or NOW - timedelta(hours=1)).isoformat()
    event = ledger.create_event(
        fingerprint=fp,
        canonical_title=raw.title,
        primary_source=raw.source,
        source_url=raw.source_url,
        first_seen=seen,
        key_facts=fp.key_facts,
        source_item_id=raw.source_item_id,
    )
    ledger.mark_published(event.event_id, 101, fp.key_facts, seen)
    return event


class FakeAI:
    available = True

    def __init__(self, *, relation="different_event", publish=True, importance=90, fail=False):
        self.config = SimpleNamespace(event_memory_hours=72, duplicate_threshold=0.87, importance_threshold=70, mode="required")
        self.relation = relation
        self.publish = publish
        self.importance = importance
        self.fail = fail
        self.relation_calls = []
        self.score_calls = []

    def embed_texts(self, texts):
        # Force a high semantic match whenever a prior event exists.
        return [[1.0, 0.0] for _ in texts]

    def judge_relation(self, new_text, prior_text):
        self.relation_calls.append((new_text, prior_text))
        if self.fail:
            raise AIServiceError("backend_down")
        return RelationDecision(
            relation=self.relation,
            confidence=0.96,
            new_fact=self.relation == "material_update",
            reason="fake relation",
        )

    def score_story(self, text):
        self.score_calls.append(text)
        if self.fail:
            raise AIServiceError("backend_down")
        return EditorialDecision(
            importance=self.importance,
            topic="security",
            publish=self.publish,
            reason="fake editorial decision",
            new_fact=True,
            priority_class="high" if self.importance >= 70 else "low",
        )


class Publisher:
    def __init__(self):
        self.items = []

    def __call__(self, item):
        self.items.append(item)
        return {"ok": True, "message_id": 9000 + len(self.items)}


def _run(tmp_path, raw, ai, *, settings=None):
    ledger, feed, editorial = _stores(tmp_path)
    publisher = Publisher()
    summary = run_cycle(
        lambda: [raw],
        ledger,
        feed,
        editorial,
        publisher,
        {"auto_publish": True, "freshness_hours": 12, "panel_max_records": 500, "ai_newsroom_mode": "required", **(settings or {})},
        NOW,
        ai=ai,
    )
    return summary, ledger, feed, editorial, publisher


def test_recent_records_enforces_72_hour_boundary(tmp_path):
    ledger, _, _ = _stores(tmp_path)
    inside = _seed_published(
        ledger,
        _raw("Iran launches missile toward Israel", url="https://example.com/in", item_id="in"),
        seen_at=NOW - timedelta(hours=71, minutes=59),
    )
    _seed_published(
        ledger,
        _raw("Old Iran missile story", url="https://example.com/out", item_id="out"),
        seen_at=NOW - timedelta(hours=72, seconds=1),
    )
    records = ledger.recent_records(NOW, hours=72)
    assert [record.event_id for record in records] == [inside.event_id]


def test_semantic_same_event_from_different_source_is_suppressed(tmp_path):
    ledger, feed, editorial = _stores(tmp_path)
    prior = _raw(
        "Iran-backed Houthi forces reached Dhubab in Yemen",
        source="Reuters",
        url="https://reuters.example/1",
        item_id="prior",
    )
    event = _seed_published(ledger, prior)
    current = _raw(
        "Forces aligned with Ansar Allah arrive at the Red Sea town of Dhubab",
        source="Associated Press",
        url="https://ap.example/2",
        item_id="current",
    )
    ai = FakeAI(relation="duplicate_same_event")
    publisher = Publisher()
    summary = run_cycle(
        lambda: [current], ledger, feed, editorial, publisher,
        {"auto_publish": True, "freshness_hours": 12, "panel_max_records": 500, "ai_newsroom_mode": "required"},
        NOW, ai=ai,
    )
    assert publisher.items == []
    assert summary.same_claim_duplicates >= 1
    assert feed.records()[0].duplicate_of == event.event_id


def test_semantic_material_update_is_not_collapsed(tmp_path):
    ledger, feed, editorial = _stores(tmp_path)
    prior = _raw(
        "Iran-backed Houthis enter Dhubab in Yemen",
        source="Reuters",
        url="https://reuters.example/dhubab",
        item_id="dhubab",
    )
    event = _seed_published(ledger, prior)
    current = _raw(
        "Saudi airstrikes hit Mokha airport in Yemen after an Iran-backed Houthi advance",
        source="Associated Press",
        url="https://ap.example/mokha",
        item_id="mokha",
    )
    ai = FakeAI(relation="material_update", publish=True, importance=91)
    publisher = Publisher()
    summary = run_cycle(
        lambda: [current], ledger, feed, editorial, publisher,
        {"auto_publish": True, "freshness_hours": 12, "panel_max_records": 500, "ai_newsroom_mode": "required", "hourly_news_limit": 20},
        NOW, ai=ai,
    )
    assert len(publisher.items) == 1
    assert summary.material_updates >= 1
    assert ledger.get(event.event_id).source_variants[-1] == current.source_url


def test_routine_diplomatic_call_never_reaches_publisher(tmp_path):
    raw = _raw(
        "Iranian foreign minister spoke by phone with Omani counterpart about the Strait of Hormuz",
        priority="protected",
    )
    summary, _ledger, _feed, _editorial, publisher = _run(tmp_path, raw, FakeAI(publish=True, importance=99))
    assert publisher.items == []
    assert summary.review_items == 1


def test_critical_missile_event_can_pass_senior_editor(tmp_path):
    raw = _raw("Iran launched ballistic missiles toward Israel after midnight")
    summary, _ledger, _feed, _editorial, publisher = _run(
        tmp_path,
        raw,
        FakeAI(publish=True, importance=99),
        settings={"hourly_news_limit": 20},
    )
    assert summary.published == 1
    assert len(publisher.items) == 1


def test_senior_editor_low_importance_routes_to_review(tmp_path):
    raw = _raw("Iran announces a new military-related statement", priority="protected")
    summary, _ledger, _feed, editorial, publisher = _run(tmp_path, raw, FakeAI(publish=False, importance=25))
    assert publisher.items == []
    assert summary.review_items == 1
    assert editorial.queue()


def test_ai_outage_fails_closed_in_required_mode(tmp_path):
    raw = _raw("Iran launched ballistic missiles toward Israel")
    summary, _ledger, feed, editorial, publisher = _run(tmp_path, raw, FakeAI(fail=True))
    assert publisher.items == []
    assert summary.review_items == 1
    assert editorial.queue()
    assert "ai_" in feed.records()[0].decision_reason


def test_ai_failure_waiting_item_is_not_retried_every_poll(tmp_path):
    raw = _raw("Iran launched ballistic missiles toward Israel")
    ledger, feed, editorial = _stores(tmp_path)
    publisher = Publisher()
    ai = FakeAI(fail=True)
    settings = {
        "auto_publish": True,
        "freshness_hours": 12,
        "panel_max_records": 500,
        "ai_newsroom_mode": "required",
        "hourly_news_limit": 20,
    }

    first = run_cycle(lambda: [raw], ledger, feed, editorial, publisher, settings, NOW, ai=ai)
    assert first.review_items == 1
    assert len(ai.score_calls) == 1

    second = run_cycle(
        lambda: [raw],
        ledger,
        feed,
        editorial,
        publisher,
        settings,
        NOW + timedelta(seconds=2),
        ai=ai,
    )
    assert second.published == 0
    assert len(ai.score_calls) == 1
    assert publisher.items == []
