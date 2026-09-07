from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from .newsroom_models import EventFingerprint, NormalizedNewsItem


def _time_bucket(value: str) -> str:
    try:
        dt = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date().isoformat()
    except ValueError:
        return "unknown"


def _normalized_objects(item: NormalizedNewsItem) -> list[str]:
    values = list(item.objects)
    text = item.normalized_text
    if ("tanker" in text or "crude oil carrier" in text or "oil carrier" in text) and "tankers" not in values:
        values.append("tankers")
    if ("warship" in text or "navy ship" in text) and "warships" not in values:
        values.append("warships")
    return sorted(set(values))


def build_fingerprint(item: NormalizedNewsItem) -> EventFingerprint:
    actors = sorted(set(item.actors))
    actions = sorted(set(item.actions))
    objects = _normalized_objects(item)
    locations = sorted(set(item.locations))
    facts = sorted(set(item.numeric_facts))
    bucket = _time_bucket(item.raw.published_at)
    structural = "|".join([
        ",".join(actors),
        ",".join(actions),
        ",".join(objects),
        ",".join(locations),
        ",".join(facts),
        bucket,
    ])
    digest = hashlib.sha1(structural.encode("utf-8")).hexdigest()
    return EventFingerprint(
        key=digest,
        actors=actors,
        actions=actions,
        objects=objects,
        locations=locations,
        key_facts=facts,
        time_bucket=bucket,
    )


def _jaccard(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def fingerprint_similarity(a: EventFingerprint, b: EventFingerprint) -> float:
    action_score = _jaccard(a.actions, b.actions)
    object_score = _jaccard(a.objects, b.objects)
    actor_score = _jaccard(a.actors, b.actors)
    location_score = _jaccard(a.locations, b.locations)
    fact_score = _jaccard(a.key_facts, b.key_facts)

    # A shared action+object is the structural core of a concrete event.
    # Locations/actors/facts refine that match; they never override opposite actions.
    score = (
        0.45 * action_score
        + 0.35 * object_score
        + 0.08 * actor_score
        + 0.08 * location_score
        + 0.04 * fact_score
    )
    if action_score == 1.0 and object_score >= 0.5:
        score = max(score, 0.80 + 0.10 * location_score + 0.05 * actor_score + 0.05 * fact_score)
    return min(1.0, score)
