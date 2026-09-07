from __future__ import annotations

from .newsroom_fingerprint import fingerprint_similarity
from .newsroom_models import DecisionResult, EventFingerprint, EventRecord, NormalizedNewsItem


PROTECTED_SOURCES = {
    "truth social",
    "centcom",
    "white house",
    "white house spokesperson",
    "state department",
    "u.s. treasury",
}


def _stored_fingerprint(record: EventRecord) -> EventFingerprint | None:
    data = record.fingerprint_data or {}
    required = {"actors", "actions", "objects", "locations", "key_facts", "time_bucket"}
    if not required.issubset(data):
        return None
    return EventFingerprint(
        key=record.fingerprint,
        actors=list(data.get("actors") or []),
        actions=list(data.get("actions") or []),
        objects=list(data.get("objects") or []),
        locations=list(data.get("locations") or []),
        key_facts=list(data.get("key_facts") or []),
        time_bucket=str(data.get("time_bucket") or ""),
    )


def _is_protected(item: NormalizedNewsItem) -> bool:
    return item.raw.source_priority == "protected" or item.raw.source.strip().lower() in PROTECTED_SOURCES


def _same_source_identity(item: NormalizedNewsItem, record: EventRecord) -> bool:
    if item.raw.source_url and item.raw.source_url in record.source_variants:
        return True
    stored_id = str((record.fingerprint_data or {}).get("source_item_id") or "")
    return bool(stored_id and item.raw.source_item_id and stored_id == item.raw.source_item_id)


def _distinct_truth_post(item: NormalizedNewsItem, record: EventRecord) -> bool:
    if item.raw.source.strip().lower() != "truth social":
        return False
    if record.primary_source.strip().lower() != "truth social":
        return False
    stored_id = str((record.fingerprint_data or {}).get("source_item_id") or "")
    return bool(stored_id and item.raw.source_item_id and stored_id != item.raw.source_item_id)


def _new_material_facts(item: EventFingerprint, record: EventRecord) -> set[str]:
    current = set(item.key_facts)
    existing = set(record.key_facts)
    if not current or not existing:
        return set()
    return current - existing


def decide_item(
    item: NormalizedNewsItem,
    fingerprint: EventFingerprint,
    candidates: list[EventRecord],
) -> DecisionResult:
    if not candidates:
        return DecisionResult(
            decision="new_event",
            reason="no_matching_event",
            confidence=1.0,
            event_id="",
        )

    for record in candidates:
        if _same_source_identity(item, record):
            return DecisionResult(
                decision="duplicate_exact",
                reason="same_source_identity_already_seen",
                confidence=1.0,
                event_id=record.event_id,
                duplicate_of=record.event_id,
            )

    for record in candidates:
        if _distinct_truth_post(item, record):
            return DecisionResult(
                decision="new_event",
                reason="distinct_protected_truth_post_id",
                confidence=1.0,
                event_id="",
            )

    scored: list[tuple[float, EventRecord]] = []
    for record in candidates:
        stored = _stored_fingerprint(record)
        if stored is None:
            continue
        scored.append((fingerprint_similarity(fingerprint, stored), record))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    if not scored:
        return DecisionResult(
            decision="needs_editorial_review" if _is_protected(item) else "new_event",
            reason="candidate_missing_structural_fingerprint",
            confidence=0.0,
            event_id="",
        )

    similarity, best = scored[0]

    if similarity < 0.70:
        return DecisionResult(
            decision="new_event",
            reason="structurally_distinct_event",
            confidence=1.0 - similarity,
            event_id="",
        )

    new_facts = _new_material_facts(fingerprint, best)
    if new_facts:
        return DecisionResult(
            decision="material_update",
            reason="new_material_facts:" + ",".join(sorted(new_facts)),
            confidence=similarity,
            event_id=best.event_id,
        )

    if similarity >= 0.82:
        return DecisionResult(
            decision="duplicate_same_claim",
            reason="same_structural_claim_without_new_material_facts",
            confidence=similarity,
            event_id=best.event_id,
            duplicate_of=best.event_id,
        )

    if _is_protected(item):
        return DecisionResult(
            decision="needs_editorial_review",
            reason="protected_source_ambiguous_event_match",
            confidence=similarity,
            event_id=best.event_id,
        )

    return DecisionResult(
        decision="new_event",
        reason="similar_topic_but_insufficient_event_match",
        confidence=1.0 - similarity,
        event_id="",
    )
