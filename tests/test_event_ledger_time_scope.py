from __future__ import annotations

from datetime import datetime, timezone

from src.event_ledger import EventLedger
from src.newsroom_models import EventFingerprint


def fp(day: str) -> EventFingerprint:
    return EventFingerprint(
        key=f"key-{day}",
        actors=["centcom"],
        actions=["strike"],
        objects=["tankers"],
        locations=["gulf of oman"],
        key_facts=[],
        time_bucket=day,
    )


def test_similarity_candidates_do_not_cross_event_days(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.json")
    old = fp("2026-04-03")
    ledger.create_event(
        fingerprint=old,
        canonical_title="CENTCOM struck a tanker in the Gulf of Oman",
        primary_source="CENTCOM",
        source_url="https://example.com/old",
        first_seen="2026-04-03T07:00:00+00:00",
    )

    current = fp("2026-09-09")
    assert ledger.find_candidates(current) == []


def test_exact_same_day_fingerprint_still_dedupes(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.json")
    current = fp("2026-09-09")
    event = ledger.create_event(
        fingerprint=current,
        canonical_title="CENTCOM struck a tanker in the Gulf of Oman",
        primary_source="CENTCOM",
        source_url="https://example.com/current",
        first_seen="2026-09-09T11:00:00+00:00",
    )
    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    assert ledger.find_candidates(current, now=now) == [event]
