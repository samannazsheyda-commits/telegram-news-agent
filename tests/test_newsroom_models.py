from __future__ import annotations

import pytest

from src.newsroom_models import (
    DecisionResult,
    EventFingerprint,
    EventRecord,
    LiveFeedRecord,
    NormalizedNewsItem,
    RawNewsItem,
)


def test_raw_news_item_round_trips_required_source_fields():
    item = RawNewsItem(
        source="Reuters",
        source_url="https://example.com/story",
        source_item_id="reuters-1",
        published_at="2026-09-07T06:57:00+00:00",
        fetched_at="2026-09-07T07:00:00+00:00",
        title="Iran announces a restricted zone",
        summary="Details",
        media=["https://example.com/photo.jpg"],
        source_priority="high",
    )

    assert RawNewsItem.from_dict(item.to_dict()) == item


def test_normalized_news_item_round_trips_structured_facts():
    item = NormalizedNewsItem(
        raw=RawNewsItem(
            source="CENTCOM",
            source_url="https://x.com/CENTCOM/status/1",
            source_item_id="1",
            published_at="2026-09-07T10:00:00+00:00",
            fetched_at="2026-09-07T10:01:00+00:00",
            title="CENTCOM redirected 92 vessels",
        ),
        actors=["CENTCOM"],
        locations=["Strait of Hormuz"],
        actions=["redirect_vessels"],
        objects=["commercial vessels"],
        numeric_facts=["92", "3", "2"],
        topic_tags=["hormuz", "security"],
        quoted_speaker="",
        normalized_text="centcom redirected 92 vessels",
    )

    assert NormalizedNewsItem.from_dict(item.to_dict()) == item


def test_event_fingerprint_round_trips_structural_identity():
    fingerprint = EventFingerprint(
        key="centcom|redirect_vessels|commercial_vessels|hormuz|92,3,2|2026-09-07",
        actors=["CENTCOM"],
        actions=["redirect_vessels"],
        objects=["commercial vessels"],
        locations=["Strait of Hormuz"],
        key_facts=["92", "3", "2"],
        time_bucket="2026-09-07",
    )

    assert EventFingerprint.from_dict(fingerprint.to_dict()) == fingerprint


def test_duplicate_decision_requires_duplicate_of():
    with pytest.raises(ValueError, match="duplicate_of"):
        DecisionResult(
            decision="duplicate_same_claim",
            reason="same event from another outlet",
            confidence=0.98,
            event_id="event-1",
            duplicate_of="",
        )


def test_non_duplicate_decision_does_not_require_duplicate_of():
    decision = DecisionResult(
        decision="new_event",
        reason="new structured event",
        confidence=0.91,
        event_id="event-2",
        duplicate_of="",
    )
    assert DecisionResult.from_dict(decision.to_dict()) == decision


def test_event_record_round_trips_variants_and_message_ids():
    record = EventRecord(
        event_id="event-1",
        fingerprint="fp-1",
        canonical_title="US strikes three Iranian tankers",
        first_seen="2026-09-07T10:00:00+00:00",
        last_updated="2026-09-07T10:05:00+00:00",
        primary_source="AP",
        source_variants=["ap-1", "cnn-1"],
        key_facts=["3 tankers"],
        published_message_ids=[487],
        status="published",
    )
    assert EventRecord.from_dict(record.to_dict()) == record


def test_live_feed_record_round_trips_trace_fields():
    record = LiveFeedRecord(
        item_id="item-1",
        event_id="event-1",
        source="Reuters",
        source_url="https://example.com/story",
        title="Iran announces restricted zone",
        published_at_source="2026-09-07T06:57:00+00:00",
        discovered_at="2026-09-07T07:00:00+00:00",
        decision="new_event",
        decision_reason="new structured event",
        duplicate_of="",
        telegram_message_id=489,
        panel_status="auto_published",
        updated_at="2026-09-07T07:00:05+00:00",
    )
    assert LiveFeedRecord.from_dict(record.to_dict()) == record
