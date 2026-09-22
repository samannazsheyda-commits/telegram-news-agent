from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any


_HISTORY_STATUS = {
    "published_manual": "PUBLISHED",
    "published_auto": "PUBLISHED",
    "published": "PUBLISHED",
    "rejected_manual": "REJECTED_PERMANENT",
    "superseded": "REJECTED_PERMANENT",
    "rejected": "REJECTED_PERMANENT",
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def _healthy_source(source: dict[str, Any]) -> bool:
    active = source.get("active", source.get("enabled", True))
    status = str(source.get("status") or "active").strip().lower()
    return bool(active) and status in {"", "active", "healthy", "ok"} and not source.get("last_error")


def _source_identity(source: dict[str, Any]) -> str:
    for key in ("identity", "channel", "handle", "feed_url", "website_url", "url"):
        value = str(source.get(key) or "").strip().lstrip("@")
        if value:
            return value
    return ""


class LegacyMigrator:
    def __init__(self, *, legacy_root: str | Path, store: Any, history_limit: int = 2000) -> None:
        self.legacy_root = Path(legacy_root).resolve()
        self.store = store
        self.history_limit = max(0, min(int(history_limit), 10000))

    def run(self, *, dry_run: bool = False) -> dict[str, Any]:
        data_root = self.legacy_root / "data"
        source_path = data_root / "custom_sources.json"
        settings_path = data_root / "newsroom_settings.json"
        history_path = data_root / "editorial_history.json"
        input_hash = hashlib.sha256()
        for path in (source_path, settings_path, history_path):
            input_hash.update(path.name.encode("utf-8"))
            input_hash.update(path.read_bytes() if path.exists() else b"")

        discovered_sources = _read_json(source_path, [])
        if not isinstance(discovered_sources, list):
            raise ValueError("legacy custom_sources.json must contain a list")
        eligible_sources = [
            source
            for source in discovered_sources
            if isinstance(source, dict) and _healthy_source(source) and _source_identity(source)
        ]
        imported_sources = 0
        if not dry_run:
            for source in eligible_sources:
                self.store.upsert_source(
                    {
                        "kind": str(source.get("kind") or "website").strip().lower(),
                        "identity": _source_identity(source),
                        "display_name": str(source.get("name") or source.get("display_name") or _source_identity(source)),
                        "enabled": True,
                        "priority": int(source.get("priority") or 0),
                        "category": source.get("category"),
                        "reliability_score": source.get("reliability_score"),
                    }
                )
                imported_sources += 1

        settings = _read_json(settings_path, {})
        if not isinstance(settings, dict):
            raise ValueError("legacy newsroom_settings.json must contain an object")
        settings_eligible = int(bool(settings))
        settings_imported = 0
        if settings and not dry_run:
            self.store.upsert_newsroom_rule(
                "legacy_newsroom_settings",
                settings,
                actor="migration",
            )
            settings_imported = 1

        discovered_history = _read_json(history_path, [])
        if not isinstance(discovered_history, list):
            raise ValueError("legacy editorial_history.json must contain a list")
        eligible_history = [
            row
            for row in discovered_history
            if isinstance(row, dict) and str(row.get("status") or "").lower() in _HISTORY_STATUS
        ][-self.history_limit :]
        imported_history = 0
        if not dry_run:
            for row in eligible_history:
                legacy_id = str(row.get("id") or row.get("news_key") or row.get("source_url") or uuid.uuid4())
                mapped = {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"bikhabar-legacy:{legacy_id}")),
                    "legacy_id": legacy_id,
                    "source": str(row.get("source") or "Legacy"),
                    "source_url": row.get("source_url"),
                    "original_title": str(row.get("original_title") or ""),
                    "original_text": str(row.get("original_summary") or row.get("original_text") or ""),
                    "published_at_source": row.get("published_at_source") or None,
                    "final_title": str(row.get("final_persian_title") or row.get("persian_title") or ""),
                    "final_body": str(row.get("final_persian_body") or row.get("persian_body") or ""),
                    "telegram_message_id": row.get("telegram_message_id") or None,
                    "reject_reason": row.get("rejection_reason") or None,
                    "status": _HISTORY_STATUS[str(row.get("status") or "").lower()],
                    "media_json": dict(row.get("media") or {}),
                }
                self.store.import_legacy_story(mapped, actor="migration")
                imported_history += 1

        expected_sources = 0 if dry_run else len(eligible_sources)
        expected_settings = 0 if dry_run else settings_eligible
        expected_history = 0 if dry_run else len(eligible_history)
        parity_ok = (
            imported_sources == expected_sources
            and settings_imported == expected_settings
            and imported_history == expected_history
        )
        return {
            "dry_run": bool(dry_run),
            "input_sha256": input_hash.hexdigest(),
            "sources": {
                "discovered": len(discovered_sources),
                "eligible": len(eligible_sources),
                "imported": imported_sources,
            },
            "settings": {"eligible": settings_eligible, "imported": settings_imported},
            "history": {
                "discovered": len(discovered_history),
                "eligible": len(eligible_history),
                "imported": imported_history,
            },
            "parity_ok": parity_ok,
        }
