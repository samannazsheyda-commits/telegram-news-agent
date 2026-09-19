from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .newsroom_v5_db import transaction
from .newsroom_v5_store import NewsroomV5Store

_TERMINAL = {
    "published_manual": "published",
    "published_auto": "published",
    "rejected_manual": "rejected",
    "superseded": "duplicate",
}
_PERSIAN_RE = re.compile(r"[\u0600-\u06ff]")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _has_persian(value: Any) -> bool:
    return bool(_PERSIAN_RE.search(_text(value)))


def _story_id(row: dict) -> str:
    direct = _text(row.get("id") or row.get("event_id") or row.get("news_key") or row.get("source_item_id"))
    if direct:
        return direct
    source_url = _text(row.get("source_url") or row.get("url") or row.get("link"))
    if source_url:
        return "url-" + hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:24]
    material = "\x1f".join((_text(row.get("source")), _text(row.get("title") or row.get("original_title")), _text(row.get("published_at_source") or row.get("published"))))
    return "legacy-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _translation(row: dict) -> tuple[str, str] | None:
    title = _text(row.get("final_persian_title") or row.get("persian_title") or row.get("title_fa") or row.get("display_title"))
    body = _text(row.get("final_persian_body") or row.get("persian_body") or row.get("body_fa"))
    if title and _has_persian(title):
        return title, body
    return None


def _legacy_rows(root: Path) -> dict[str, list[dict]]:
    def rows(relative: str) -> list[dict]:
        value = _read_json(root / relative, [])
        return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    return {
        "live": rows("data/panel_live_feed.json"),
        "queue": rows("data/editorial_queue.json"),
        "history": rows("data/editorial_history.json"),
        "sources": rows("data/custom_sources.json"),
    }


def build_migration_projection(root: str | Path) -> dict:
    root = Path(root)
    legacy = _legacy_rows(root)
    projections: dict[str, dict] = {}
    origins: dict[str, set[str]] = {}

    # Lowest to highest precedence. Terminal history is applied last.
    for origin, rows in (("live", legacy["live"]), ("queue", legacy["queue"]), ("history", legacy["history"])):
        for row in rows:
            story_id = _story_id(row)
            current = projections.get(story_id, {})
            merged = dict(current)
            for key, value in row.items():
                if value not in (None, "", [], {}):
                    merged[key] = value
            merged["id"] = story_id
            projections[story_id] = merged
            origins.setdefault(story_id, set()).add(origin)

    stories: list[dict] = []
    translations: list[dict] = []
    tombstones: list[dict] = []
    publications: list[dict] = []

    history_by_id = {_story_id(row): row for row in legacy["history"]}
    for story_id, row in projections.items():
        history = history_by_id.get(story_id, {})
        status = _text(history.get("status") or row.get("status"))
        translated = _translation(row)
        if status in _TERMINAL:
            state = _TERMINAL[status]
        elif translated:
            state = "review"
        else:
            state = "received"

        news_key = _text(row.get("news_key") or row.get("source_item_id")) or None
        source_item_id = _text(row.get("source_item_id") or row.get("news_key")) or None
        source_url = _text(row.get("source_url") or row.get("url") or row.get("link")) or None
        source_name = _text(row.get("source_name") or row.get("source")) or None
        story = {
            "id": story_id,
            "news_key": news_key,
            "source_id": _text(row.get("source_id") or source_name) or None,
            "source_name": source_name,
            "source_url": source_url,
            "source_item_id": source_item_id,
            "original_title": _text(row.get("original_title") or row.get("title")) or None,
            "original_body": _text(row.get("original_body") or row.get("original_summary") or row.get("summary")) or None,
            "published_at_source": _text(row.get("published_at_source") or row.get("published")) or None,
            "discovered_at": _text(row.get("discovered_at") or row.get("created_at")) or None,
            "state": state,
            "created_at": _text(row.get("created_at") or row.get("discovered_at")) or None,
            "updated_at": _text(row.get("updated_at") or row.get("decision_at")) or None,
        }
        stories.append(story)

        if translated:
            translations.append({
                "story_id": story_id,
                "title_fa": translated[0],
                "body_fa": translated[1],
                "backend": "legacy_import",
                "quality_passed": True,
            })

        if status == "rejected_manual" and (news_key or source_url):
            tombstones.append({
                "story_id": story_id,
                "news_key": news_key,
                "source_url": source_url,
                "reason": "rejected_manual",
            })

        if state == "published":
            telegram_message_id = history.get("telegram_message_id") or history.get("message_id")
            publications.append({
                "story_id": story_id,
                "idempotency_key": f"legacy:{story_id}",
                "copy_mode": "manual" if status == "published_manual" else "machine",
                "title_fa": translated[0] if translated else _text(row.get("persian_title") or row.get("final_persian_title")),
                "body_fa": translated[1] if translated else _text(row.get("persian_body") or row.get("final_persian_body")),
                "telegram_message_id": _text(telegram_message_id) or None,
                "published_at": _text(history.get("decision_at") or history.get("published_at") or history.get("updated_at")) or None,
            })

    sources: list[dict] = []
    for index, row in enumerate(legacy["sources"]):
        source_id = _text(row.get("id") or row.get("source_id") or row.get("name"))
        if not source_id:
            url = _text(row.get("url") or row.get("feed_url"))
            source_id = "source-" + hashlib.sha256((url or str(index)).encode("utf-8")).hexdigest()[:20]
        item = dict(row)
        item["id"] = source_id
        sources.append(item)

    return {
        "stories": stories,
        "translations": translations,
        "tombstones": tombstones,
        "publications": publications,
        "sources": sources,
        "legacy_counts": {key: len(value) for key, value in legacy.items()},
        "state": _read_json(root / "state.json", {}),
        "origins": {key: sorted(value) for key, value in origins.items()},
    }


def migrate_local_snapshot(root: str | Path, store: NewsroomV5Store, *, apply: bool = False) -> dict:
    projection = build_migration_projection(root)
    report = {
        "stories": len(projection["stories"]),
        "translations": len(projection["translations"]),
        "tombstones": len(projection["tombstones"]),
        "publications": len(projection["publications"]),
        "sources": len(projection["sources"]),
        "conflicts": [],
        "applied": bool(apply),
    }
    if not apply:
        return report

    translations = {item["story_id"]: item for item in projection["translations"]}
    publications = {item["story_id"]: item for item in projection["publications"]}
    tombstones = {item["story_id"]: item for item in projection["tombstones"]}

    with transaction(store.conn):
        for story in projection["stories"]:
            cleaned = {key: value for key, value in story.items() if value is not None}
            store.upsert_story(cleaned)
            translation = translations.get(story["id"])
            if translation:
                store.set_translation(**translation)
            tombstone = tombstones.get(story["id"])
            if tombstone:
                store.add_story_tombstone(**tombstone)
            publication = publications.get(story["id"])
            if publication:
                created = store.create_publication_once(
                    publication["story_id"],
                    idempotency_key=publication["idempotency_key"],
                    copy_mode=publication["copy_mode"],
                    title_fa=publication["title_fa"],
                    body_fa=publication["body_fa"],
                    status="published",
                )
                store.update_publication(
                    created["id"],
                    status="published",
                    telegram_message_id=publication.get("telegram_message_id"),
                    published_at=publication.get("published_at"),
                )
        for source in projection["sources"]:
            store.upsert_source(source)

        store.append_audit(
            "migration_apply",
            entity_type="newsroom_store",
            detail={key: report[key] for key in ("stories", "translations", "tombstones", "publications", "sources")},
        )

    return report
