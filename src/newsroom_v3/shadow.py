from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from ..newsroom_eligibility import evaluate_eligibility
from ..newsroom_fingerprint import build_fingerprint
from ..newsroom_models import RawNewsItem
from ..newsroom_normalize import normalize_item
from .store import NewsroomV3Store


@dataclass(frozen=True)
class ShadowCycleResult:
    processed: int = 0
    ready: int = 0
    waiting: int = 0
    rejected: int = 0
    duplicates: int = 0
    telegram_writes: int = 0
    story_ids: list[str] = field(default_factory=list)


def _story_id(raw: RawNewsItem) -> str:
    identity = "\x1f".join(
        (
            str(raw.source or "").strip(),
            str(raw.source_item_id or "").strip(),
            str(raw.source_url or "").strip(),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


class NewsroomV3ShadowPipeline:
    """Deterministic, no-publish V3 intake and exact-dedup slice."""

    def __init__(self, store: NewsroomV3Store):
        self.store = store

    def run(self, items: Iterable[RawNewsItem], *, now: datetime) -> ShadowCycleResult:
        processed = 0
        ready = 0
        waiting = 0
        rejected = 0
        duplicates = 0
        story_ids: list[str] = []

        for raw in items:
            processed += 1
            item = normalize_item(raw)
            fingerprint = build_fingerprint(item)
            eligibility = evaluate_eligibility(item, now)
            story_id = _story_id(raw)
            duplicate_of = ""

            if eligibility.eligible:
                canonical = self.store.find_canonical_story(
                    source_url=raw.source_url,
                    fingerprint=fingerprint.key,
                    exclude_story_id=story_id,
                )
                if canonical is not None:
                    decision_state = "duplicate"
                    duplicate_of = canonical.story_id
                    decision_reason = (
                        "duplicate_exact_url"
                        if str(canonical.source_url or "").strip() == str(raw.source_url or "").strip()
                        else "duplicate_fingerprint"
                    )
                    duplicates += 1
                else:
                    decision_state = "ready"
                    decision_reason = eligibility.reason
                    ready += 1
            elif eligibility.review:
                decision_state = "waiting"
                decision_reason = eligibility.reason
                waiting += 1
            else:
                decision_state = "rejected"
                decision_reason = eligibility.reason
                rejected += 1

            self.store.upsert_story(
                story_id=story_id,
                source_item_id=raw.source_item_id,
                source=raw.source,
                source_url=raw.source_url,
                title=raw.title,
                summary=raw.summary,
                published_at=raw.published_at,
                fingerprint=fingerprint.key,
                decision_state=decision_state,
                decision_reason=decision_reason,
                duplicate_of=duplicate_of,
            )
            story_ids.append(story_id)

        return ShadowCycleResult(
            processed=processed,
            ready=ready,
            waiting=waiting,
            rejected=rejected,
            duplicates=duplicates,
            telegram_writes=0,
            story_ids=story_ids,
        )
