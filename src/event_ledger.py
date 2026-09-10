from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

from .newsroom_fingerprint import fingerprint_similarity
from .newsroom_models import EventFingerprint, EventRecord


KINETIC_ACTIONS = {"strike", "explosion", "intercept"}
KINETIC_OBJECTS = {"missiles", "explosions"}


def _parse_time(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bucket_time(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw or raw == "unknown" or "T" not in raw:
        return None
    return _parse_time(raw)


def _is_kinetic(fp: EventFingerprint) -> bool:
    return bool(set(fp.actions) & KINETIC_ACTIONS or set(fp.objects) & KINETIC_OBJECTS)


def _nearby_bucket(left: EventFingerprint, right: EventFingerprint) -> bool:
    if left.time_bucket == right.time_bucket:
        return True
    a = _bucket_time(left.time_bucket)
    b = _bucket_time(right.time_bucket)
    if a is None or b is None:
        return False
    window = timedelta(minutes=75) if (_is_kinetic(left) or _is_kinetic(right)) else timedelta(hours=12)
    return abs(a - b) <= window


def _normalized_claim(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").lower()).strip()
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", text).strip()


def _claim_similarity(left: str, right: str) -> float:
    a = _normalized_claim(left)
    b = _normalized_claim(right)
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    token_overlap = len(ta & tb) / max(1, min(len(ta), len(tb))) if ta and tb else 0.0
    return max(token_overlap, SequenceMatcher(None, a, b).ratio())


def _source_key(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return re.sub(r"\s*/\s*(?:x|telegram)\s*$", "", text).strip()


class EventLedger:
    def __init__(self, path: str | Path = "data/event_ledger.json"):
        self.path = Path(path)

    def _read(self) -> list[EventRecord]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        if not isinstance(payload, list):
            return []
        records: list[EventRecord] = []
        for item in payload:
            if isinstance(item, dict):
                records.append(EventRecord.from_dict(item))
        return records

    def _write(self, records: list[EventRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [record.to_dict() for record in records]
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        fd, tmp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def records(self) -> list[EventRecord]:
        return self._read()

    def get(self, event_id: str) -> EventRecord | None:
        return next((record for record in self._read() if record.event_id == event_id), None)

    def find_by_source_url(self, source_url: str) -> EventRecord | None:
        url = str(source_url or "").strip()
        if not url:
            return None
        return next((record for record in self._read() if url in record.source_variants), None)

    def publication_count_since(self, since: datetime) -> int:
        """Count successful Telegram news publications in a rolling time window.

        Publication timestamps live inside fingerprint_data so older ledger files
        remain schema-compatible. Records created before this counter existed do
        not fabricate timestamps from last_updated, because that field can move
        when a source variant arrives and is not proof of a publication.
        """
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        since_utc = since.astimezone(timezone.utc)
        count = 0
        for record in self._read():
            data = record.fingerprint_data or {}
            raw_times = data.get("publication_times") or []
            if not isinstance(raw_times, list):
                continue
            for raw_time in raw_times:
                published = _parse_time(str(raw_time or ""))
                if published is not None and published >= since_utc:
                    count += 1
        return count

    def find_same_source_claims(
        self,
        source: str,
        title: str,
        published_at: str,
        *,
        max_age_hours: int = 12,
        min_text_similarity: float = 0.82,
    ) -> list[EventRecord]:
        """Return recent near-verbatim claims from the same publisher.

        This closes the gap where the same White House/official claim gets a new
        post URL and lands in a later fingerprint time bucket. We only widen the
        candidate window when wording itself is strongly similar, so a genuinely
        new attack/update from the same source is not collapsed just because the
        actors and topic are similar.
        """
        source_key = _source_key(source)
        published = _parse_time(published_at)
        if not source_key or published is None or not str(title or "").strip():
            return []
        window = timedelta(hours=max(1, int(max_age_hours)))
        matches: list[EventRecord] = []
        for record in self._read():
            if _source_key(record.primary_source) != source_key:
                continue
            record_time = _parse_time(record.last_updated) or _parse_time(record.first_seen)
            if record_time is None or abs(published - record_time) > window:
                continue
            if _claim_similarity(title, record.canonical_title) < min_text_similarity:
                continue
            matches.append(record)
        return matches

    def _replace(self, updated: EventRecord) -> EventRecord:
        records = self._read()
        replaced = False
        output: list[EventRecord] = []
        for record in records:
            if record.event_id == updated.event_id:
                output.append(updated)
                replaced = True
            else:
                output.append(record)
        if not replaced:
            output.append(updated)
        self._write(output)
        return updated

    @staticmethod
    def _record_fingerprint(record: EventRecord) -> EventFingerprint | None:
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

    def find_candidates(self, fingerprint: EventFingerprint, min_similarity: float = 0.70) -> list[EventRecord]:
        matches: list[EventRecord] = []
        for record in self._read():
            stored = self._record_fingerprint(record)
            if record.fingerprint == fingerprint.key:
                matches.append(record)
                continue
            if stored is None:
                continue
            similarity = fingerprint_similarity(stored, fingerprint)
            if similarity < min_similarity:
                continue
            if not _nearby_bucket(stored, fingerprint):
                continue
            matches.append(record)
        return matches

    @staticmethod
    def _source_item_id_from_url(source_url: str) -> str:
        raw = str(source_url or "").strip()
        if not raw:
            return ""
        try:
            path = urlparse(raw).path.rstrip("/")
        except ValueError:
            return ""
        return path.rsplit("/", 1)[-1] if path else ""

    def create_event(
        self,
        *,
        fingerprint: EventFingerprint,
        canonical_title: str,
        primary_source: str,
        source_url: str,
        first_seen: str,
        key_facts: list[str] | None = None,
        source_item_id: str = "",
    ) -> EventRecord:
        seed = f"{fingerprint.key}|{first_seen}|{source_url}"
        event_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()
        existing = self.get(event_id)
        if existing is not None:
            return existing
        resolved_source_item_id = str(source_item_id or "").strip() or self._source_item_id_from_url(source_url)
        event = EventRecord(
            event_id=event_id,
            fingerprint=fingerprint.key,
            canonical_title=canonical_title,
            first_seen=first_seen,
            last_updated=first_seen,
            primary_source=primary_source,
            source_variants=[source_url] if source_url else [],
            key_facts=list(dict.fromkeys(key_facts or fingerprint.key_facts)),
            published_message_ids=[],
            status="new",
            fingerprint_data={
                "actors": list(fingerprint.actors),
                "actions": list(fingerprint.actions),
                "objects": list(fingerprint.objects),
                "locations": list(fingerprint.locations),
                "key_facts": list(fingerprint.key_facts),
                "time_bucket": fingerprint.time_bucket,
                "source_item_id": resolved_source_item_id,
            },
        )
        records = self._read()
        records.append(event)
        self._write(records)
        return event

    def add_variant(self, event_id: str, source_url: str, updated_at: str) -> EventRecord:
        event = self.get(event_id)
        if event is None:
            raise KeyError(event_id)
        variants = list(event.source_variants)
        if source_url and source_url not in variants:
            variants.append(source_url)
        return self._replace(replace(event, source_variants=variants, last_updated=updated_at))

    def mark_published(self, event_id: str, message_id: int, facts: list[str], updated_at: str) -> EventRecord:
        event = self.get(event_id)
        if event is None:
            raise KeyError(event_id)
        ids = list(event.published_message_ids)
        fingerprint_data = dict(event.fingerprint_data or {})
        publication_times = list(fingerprint_data.get("publication_times") or [])
        if message_id not in ids:
            ids.append(message_id)
            # A timestamp is appended only for a newly recorded Telegram message,
            # making retries/idempotent mark_published calls safe for rate counts.
            if _parse_time(updated_at) is not None:
                publication_times.append(updated_at)
        fingerprint_data["publication_times"] = publication_times[-200:]
        merged_facts = list(dict.fromkeys([*event.key_facts, *facts]))
        return self._replace(
            replace(
                event,
                published_message_ids=ids,
                key_facts=merged_facts,
                last_updated=updated_at,
                status="published",
                fingerprint_data=fingerprint_data,
            )
        )

    def update_material_facts(self, event_id: str, facts: list[str], updated_at: str) -> EventRecord:
        event = self.get(event_id)
        if event is None:
            raise KeyError(event_id)
        merged = list(dict.fromkeys([*event.key_facts, *facts]))
        return self._replace(replace(event, key_facts=merged, last_updated=updated_at))