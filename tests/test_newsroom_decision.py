import json
from pathlib import Path

import pytest

from src.newsroom_decision import decide_item
from src.newsroom_fingerprint import build_fingerprint
from src.newsroom_models import EventRecord, RawNewsItem
from src.newsroom_normalize import normalize_item


FIXTURES = json.loads(Path("tests/fixtures/newsroom_v2_regressions.json").read_text(encoding="utf-8"))


def raw(payload, *, published="2026-09-07T12:00:00+00:00"):
    return RawNewsItem(
        source=payload["source"],
        source_url=payload["url"],
        source_item_id=payload["id"],
        published_at=published,
        fetched_at="2026-09-07T12:01:00+00:00",
        title=payload["title"],
        source_priority=payload.get("priority", "normal"),
    )


def event_from(payload, event_id="event-1", *, published="2026-09-07T12:00:00+00:00"):
    item = normalize_item(raw(payload, published=published))
    fp = build_fingerprint(item)
    return EventRecord(
        event_id=event_id,
        fingerprint=fp.key,
        canonical_title=item.raw.title,
        first_seen=item.raw.fetched_at,
        last_updated=item.raw.fetched_at,
        primary_source=item.raw.source,
        source_variants=[item.raw.source_url],
        key_facts=list(fp.key_facts),
        published_message_ids=[101],
        status="published",
        fingerprint_data={
            "actors": list(fp.actors),
            "actions": list(fp.actions),
            "objects": list(fp.objects),
            "locations": list(fp.locations),
            "key_facts": list(fp.key_facts),
            "time_bucket": fp.time_bucket,
            "source_item_id": item.raw.source_item_id,
        },
    )


@pytest.mark.parametrize("case", FIXTURES, ids=[case["name"] for case in FIXTURES])
def test_real_regression_decisions(case):
    current = normalize_item(raw(case["current"]))
    fp = build_fingerprint(current)
    prior = event_from(case["prior"])
    result = decide_item(current, fp, [prior])
    assert result.decision == case["expected"]
    if result.decision.startswith("duplicate_"):
        assert result.duplicate_of == prior.event_id
        assert result.reason


def test_same_source_url_is_exact_duplicate():
    payload = {
        "source": "Reuters",
        "url": "https://reuters.com/exact-story",
        "id": "same-1",
        "title": "Iran announces new restricted zone in Gulf",
    }
    current = normalize_item(raw(payload))
    result = decide_item(current, build_fingerprint(current), [event_from(payload)])
    assert result.decision == "duplicate_exact"
    assert result.duplicate_of == "event-1"


def test_protected_low_confidence_candidate_requires_review_not_duplicate():
    current_payload = {
        "source": "CENTCOM",
        "priority": "protected",
        "url": "https://centcom.mil/new",
        "id": "centcom-new",
        "title": "CENTCOM says Iranian drone approached US warship in Gulf",
    }
    prior_payload = {
        "source": "Reuters",
        "url": "https://reuters.com/iran-warship",
        "id": "prior",
        "title": "Iran warns US warships in Gulf",
    }
    current = normalize_item(raw(current_payload))
    result = decide_item(current, build_fingerprint(current), [event_from(prior_payload)])
    assert result.decision in {"new_event", "needs_editorial_review"}
    assert not result.decision.startswith("duplicate_")


def test_same_truth_post_id_is_exact_duplicate_even_if_refetched():
    current_payload = {
        "source": "Truth Social",
        "priority": "protected",
        "url": "https://truthsocial.com/@realDonaldTrump/117230287806050615",
        "id": "117230287806050615",
        "title": "Iran's Navy",
    }
    current = normalize_item(raw(current_payload))
    prior = event_from(current_payload)
    result = decide_item(current, build_fingerprint(current), [prior])
    assert result.decision == "duplicate_exact"


def test_live_houthi_attack_same_event_is_deduped_across_reuters_and_cnn():
    prior_payload = {
        "source": "Reuters",
        "url": "https://reuters.com/houthi-saudi",
        "id": "r-houthi",
        "title": "Iran-backed Houthis attack Saudi energy facilities, wounding dozens and sending oil prices higher",
    }
    current_payload = {
        "source": "CNN",
        "url": "https://cnn.com/houthi-saudi",
        "id": "cnn-houthi",
        "title": "Iran-backed Houthis attack Saudi Arabia injuring dozens, Kingdom vows response",
    }
    current = normalize_item(raw(current_payload, published="2026-09-08T01:50:00+00:00"))
    prior = event_from(prior_payload, published="2026-09-08T01:49:00+00:00")
    result = decide_item(current, build_fingerprint(current), [prior])
    assert result.decision == "duplicate_same_claim"
    assert result.duplicate_of == prior.event_id


def test_live_improved_ballistic_missile_same_claim_is_deduped_across_ap_and_toi():
    prior_payload = {
        "source": "Associated Press",
        "url": "https://apnews.com/improved-missile",
        "id": "ap-missile",
        "title": "Iran says improved ballistic missile shows it will take preemptive action against threats",
    }
    current_payload = {
        "source": "Times of Israel",
        "url": "https://timesofisrael.com/improved-missile",
        "id": "toi-missile",
        "title": "Touting improved ballistic missile, Iran vows preemptive action against threats",
    }
    current = normalize_item(raw(current_payload, published="2026-09-08T03:00:00+00:00"))
    prior = event_from(prior_payload, published="2026-09-08T02:55:00+00:00")
    result = decide_item(current, build_fingerprint(current), [prior])
    assert result.decision == "duplicate_same_claim"
    assert result.duplicate_of == prior.event_id
