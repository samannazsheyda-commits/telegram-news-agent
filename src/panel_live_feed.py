from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .newsroom_models import LiveFeedRecord


class LiveFeedStore:
    def __init__(self, path: str | Path = "data/panel_live_feed.json"):
        self.path = Path(path)

    def _read(self) -> list[LiveFeedRecord]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        if not isinstance(payload, list):
            return []
        rows: list[LiveFeedRecord] = []
        for item in payload:
            if isinstance(item, dict):
                rows.append(LiveFeedRecord.from_dict(item))
        return sorted(rows, key=lambda row: row.updated_at, reverse=True)

    def _write(self, rows: list[LiveFeedRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(rows, key=lambda row: row.updated_at, reverse=True)
        payload = json.dumps([row.to_dict() for row in ordered], ensure_ascii=False, indent=2) + "\n"
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

    def records(self) -> list[LiveFeedRecord]:
        return self._read()

    def upsert(self, record: LiveFeedRecord) -> LiveFeedRecord:
        rows = self._read()
        result: list[LiveFeedRecord] = []
        newer_existing = False
        for current in rows:
            if current.item_id == record.item_id:
                if current.updated_at > record.updated_at:
                    result.append(current)
                    newer_existing = True
                continue
            result.append(current)
        if not newer_existing:
            result.append(record)
        self._write(result)
        return record

    def prune(self, now: datetime, freshness_hours: int = 3, max_records: int = 500) -> int:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        cutoff = now - timedelta(hours=max(1, int(freshness_hours)))
        original = self._read()
        kept: list[LiveFeedRecord] = []
        for row in original:
            try:
                updated = datetime.fromisoformat(row.updated_at.replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if updated >= cutoff:
                kept.append(row)
        kept = sorted(kept, key=lambda row: row.updated_at, reverse=True)[: max(1, int(max_records))]
        removed = max(0, len(original) - len(kept))
        self._write(kept)
        return removed
