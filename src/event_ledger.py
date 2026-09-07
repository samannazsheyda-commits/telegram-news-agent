from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from .newsroom_models import EventFingerprint, EventRecord


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

    def find_candidates(self, fingerprint: EventFingerprint) -> list[EventRecord]:
        return [record for record in self._read() if record.fingerprint == fingerprint.key]

    def create_event(
        self,
        *,
        fingerprint: EventFingerprint,
        canonical_title: str,
        primary_source: str,
        source_url: str,
        first_seen: str,
        key_facts: list[str] | None = None,
    ) -> EventRecord:
        seed = f"{fingerprint.key}|{first_seen}|{source_url}"
        event_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()
        existing = self.get(event_id)
        if existing is not None:
            return existing
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
        if message_id not in ids:
            ids.append(message_id)
        merged_facts = list(dict.fromkeys([*event.key_facts, *facts]))
        return self._replace(
            replace(
                event,
                published_message_ids=ids,
                key_facts=merged_facts,
                last_updated=updated_at,
                status="published",
            )
        )

    def update_material_facts(self, event_id: str, facts: list[str], updated_at: str) -> EventRecord:
        event = self.get(event_id)
        if event is None:
            raise KeyError(event_id)
        merged = list(dict.fromkeys([*event.key_facts, *facts]))
        return self._replace(replace(event, key_facts=merged, last_updated=updated_at))
