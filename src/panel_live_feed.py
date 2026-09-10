from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .newsroom_models import LiveFeedRecord


class LiveFeedStore:
    def __init__(self, path: str | Path = "data/panel_live_feed.json", dismissed_path: str | Path | None = None):
        self.path = Path(path)
        self.dismissed_path = Path(dismissed_path) if dismissed_path is not None else self.path.with_name("panel_dismissed.json")

    @staticmethod
    def _atomic_json_write(path: Path, value) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

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
        ordered = sorted(rows, key=lambda row: row.updated_at, reverse=True)
        self._atomic_json_write(self.path, [row.to_dict() for row in ordered])

    def _dismissed(self) -> list[dict]:
        try:
            value = json.loads(self.dismissed_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        if isinstance(value, dict):
            value = value.get("items", [])
        if not isinstance(value, list):
            return []
        return [dict(row) for row in value if isinstance(row, dict)]

    def _is_dismissed(self, record: LiveFeedRecord) -> bool:
        item_id = str(record.item_id or "").strip()
        source_url = str(record.source_url or "").strip()
        for row in self._dismissed():
            dismissed_id = str(row.get("item_id") or "").strip()
            dismissed_url = str(row.get("source_url") or "").strip()
            if item_id and dismissed_id and item_id == dismissed_id:
                return True
            if source_url and dismissed_url and source_url == dismissed_url:
                return True
        return False

    def records(self) -> list[LiveFeedRecord]:
        return self._read()

    def upsert(self, record: LiveFeedRecord) -> LiveFeedRecord:
        if self._is_dismissed(record):
            return record
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

    def dismiss(self, item_ids: list[str] | tuple[str, ...], source_urls: list[str] | tuple[str, ...] = ()) -> int:
        ids = {str(value or "").strip() for value in item_ids if str(value or "").strip()}
        urls = {str(value or "").strip() for value in source_urls if str(value or "").strip()}
        rows = self._read()
        matched = [row for row in rows if row.item_id in ids or (row.source_url and row.source_url in urls)]
        for row in matched:
            if row.item_id:
                ids.add(row.item_id)
            if row.source_url:
                urls.add(row.source_url)
        kept = [row for row in rows if row.item_id not in ids and (not row.source_url or row.source_url not in urls)]
        self._write(kept)

        existing = self._dismissed()
        by_identity: dict[tuple[str, str], dict] = {}
        for row in existing:
            key = (str(row.get("item_id") or "").strip(), str(row.get("source_url") or "").strip())
            if key != ("", ""):
                by_identity[key] = row
        now = datetime.now(timezone.utc).isoformat()
        for item_id in ids:
            by_identity[(item_id, "")] = {"item_id": item_id, "source_url": "", "dismissed_at": now}
        for url in urls:
            by_identity[("", url)] = {"item_id": "", "source_url": url, "dismissed_at": now}
        ordered = sorted(by_identity.values(), key=lambda row: str(row.get("dismissed_at") or ""), reverse=True)[:5000]
        self._atomic_json_write(self.dismissed_path, ordered)
        return len(matched)

    @staticmethod
    def _record_time(row: LiveFeedRecord) -> datetime | None:
        for raw in (row.published_at_source, row.updated_at):
            value = str(raw or "").strip()
            if not value:
                continue
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                try:
                    dt = parsedate_to_datetime(value)
                except Exception:
                    continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        return None

    def prune(self, now: datetime, freshness_hours: int = 3, max_records: int = 500) -> int:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now_utc = now.astimezone(timezone.utc)
        cutoff = now_utc - timedelta(hours=max(1, int(freshness_hours)))
        original = self._read()
        kept: list[LiveFeedRecord] = []
        for row in original:
            record_time = self._record_time(row)
            if record_time is not None and cutoff <= record_time <= now_utc + timedelta(minutes=10) and not self._is_dismissed(row):
                kept.append(row)
        kept = sorted(kept, key=lambda row: row.updated_at, reverse=True)[: max(1, int(max_records))]
        removed = max(0, len(original) - len(kept))
        self._write(kept)
        return removed
