from src.newsroom_models import EventFingerprint
from src.event_ledger import EventLedger


def fp(key="iran|strike|tanker|gulf|3|2026-09-07T12"):
    return EventFingerprint(
        key=key,
        actors=["Iran"],
        actions=["strike"],
        objects=["tanker"],
        locations=["Persian Gulf"],
        key_facts=["3"],
        time_bucket="2026-09-07T12",
    )


def test_empty_ledger_starts_empty(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.json")
    assert ledger.records() == []


def test_create_event_persists_and_survives_restart(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = EventLedger(path)
    event = ledger.create_event(
        fingerprint=fp(),
        canonical_title="US strikes three Iranian tankers",
        primary_source="Reuters",
        source_url="https://reuters.example/a",
        first_seen="2026-09-07T12:01:00+00:00",
    )
    restarted = EventLedger(path)
    loaded = restarted.get(event.event_id)
    assert loaded is not None
    assert loaded.event_id == event.event_id
    assert loaded.fingerprint == fp().key
    assert loaded.source_variants == ["https://reuters.example/a"]


def test_add_variant_is_idempotent(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.json")
    event = ledger.create_event(
        fingerprint=fp(),
        canonical_title="US strikes three Iranian tankers",
        primary_source="Reuters",
        source_url="https://reuters.example/a",
        first_seen="2026-09-07T12:01:00+00:00",
    )
    ledger.add_variant(event.event_id, "https://ap.example/b", "2026-09-07T12:02:00+00:00")
    ledger.add_variant(event.event_id, "https://ap.example/b", "2026-09-07T12:03:00+00:00")
    loaded = ledger.get(event.event_id)
    assert loaded is not None
    assert loaded.source_variants == ["https://reuters.example/a", "https://ap.example/b"]


def test_mark_published_records_message_id_and_facts(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.json")
    event = ledger.create_event(
        fingerprint=fp(),
        canonical_title="US strikes three Iranian tankers",
        primary_source="Reuters",
        source_url="https://reuters.example/a",
        first_seen="2026-09-07T12:01:00+00:00",
    )
    ledger.mark_published(event.event_id, 777, ["3"], "2026-09-07T12:04:00+00:00")
    loaded = ledger.get(event.event_id)
    assert loaded is not None
    assert loaded.published_message_ids == [777]
    assert loaded.key_facts == ["3"]
    assert loaded.status == "published"


def test_update_material_facts_merges_without_duplicates(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.json")
    event = ledger.create_event(
        fingerprint=fp(),
        canonical_title="CENTCOM operational update",
        primary_source="CENTCOM",
        source_url="https://centcom.example/1",
        first_seen="2026-09-07T12:01:00+00:00",
        key_facts=["92"],
    )
    ledger.update_material_facts(event.event_id, ["92", "3", "2"], "2026-09-07T12:05:00+00:00")
    loaded = ledger.get(event.event_id)
    assert loaded is not None
    assert loaded.key_facts == ["92", "3", "2"]


def test_find_candidates_returns_same_structural_key(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.json")
    created = ledger.create_event(
        fingerprint=fp(),
        canonical_title="US strikes three Iranian tankers",
        primary_source="Reuters",
        source_url="https://reuters.example/a",
        first_seen="2026-09-07T12:01:00+00:00",
    )
    matches = ledger.find_candidates(fp())
    assert [record.event_id for record in matches] == [created.event_id]
