from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


class _Serializable:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        allowed = {field.name for field in fields(cls)}
        clean = {name: data[name] for name in allowed if name in data}
        return cls(**clean)


@dataclass(frozen=True)
class RawNewsItem(_Serializable):
    source: str
    source_url: str
    source_item_id: str
    published_at: str
    fetched_at: str
    title: str
    summary: str = ""
    media: list[str] | None = None
    source_priority: str = "normal"

    def __post_init__(self) -> None:
        if self.media is None:
            object.__setattr__(self, "media", [])


@dataclass(frozen=True)
class NormalizedNewsItem(_Serializable):
    raw: RawNewsItem
    actors: list[str]
    locations: list[str]
    actions: list[str]
    objects: list[str]
    numeric_facts: list[str]
    topic_tags: list[str]
    quoted_speaker: str
    normalized_text: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedNewsItem":
        payload = dict(data)
        raw = payload.get("raw")
        if isinstance(raw, dict):
            payload["raw"] = RawNewsItem.from_dict(raw)
        return cls(**{field.name: payload[field.name] for field in fields(cls) if field.name in payload})


@dataclass(frozen=True)
class EventFingerprint(_Serializable):
    key: str
    actors: list[str]
    actions: list[str]
    objects: list[str]
    locations: list[str]
    key_facts: list[str]
    time_bucket: str


@dataclass(frozen=True)
class DecisionResult(_Serializable):
    decision: str
    reason: str
    confidence: float
    event_id: str
    duplicate_of: str = ""

    def __post_init__(self) -> None:
        if self.decision.startswith("duplicate_") and not self.duplicate_of:
            raise ValueError("duplicate_of is required for duplicate decisions")


@dataclass(frozen=True)
class EventRecord(_Serializable):
    event_id: str
    fingerprint: str
    canonical_title: str
    first_seen: str
    last_updated: str
    primary_source: str
    source_variants: list[str]
    key_facts: list[str]
    published_message_ids: list[int]
    status: str


@dataclass(frozen=True)
class LiveFeedRecord(_Serializable):
    item_id: str
    event_id: str
    source: str
    source_url: str
    title: str
    published_at_source: str
    discovered_at: str
    decision: str
    decision_reason: str
    duplicate_of: str
    telegram_message_id: int | None
    panel_status: str
    updated_at: str
