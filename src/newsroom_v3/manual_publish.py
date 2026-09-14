from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .canary import build_production_publisher
from .outbox import AMBIGUOUS_ERROR_PREFIX, NewsroomV3PublisherWorker
from .production import PRODUCTION_STATE, _atomic_json, _read_json
from .store import NewsroomV3Store, StoryRecord


def _utc(value: datetime | None) -> datetime:
    resolved = value or datetime.now(timezone.utc)
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc)


def _manual_story_id(item_id: str, source_url: str) -> str:
    payload = f"{str(item_id).strip()}\n{str(source_url).strip()}".encode("utf-8")
    return "panel-" + hashlib.sha256(payload).hexdigest()[:32]


def _fingerprint(source_url: str, title: str, body: str) -> str:
    payload = f"{source_url}\n{title}\n{body}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _update_status(data_dir: Path, **fields) -> None:
    status_path = data_dir / PRODUCTION_STATE
    current = _read_json(status_path)
    _atomic_json(status_path, {**current, **fields})


def publish_manual_story(
    *,
    data_dir: str | Path,
    item_id: str,
    news_key: str,
    source: str,
    source_url: str,
    title: str,
    body: str = "",
    published_at: str = "",
    publisher: Callable[[StoryRecord], object] | None = None,
    now: datetime | None = None,
) -> dict:
    """Publish one editor-approved story through the durable V3 outbox.

    This function is intentionally separate from the Flask process. The panel
    enqueues a command; the production runtime executes this function. An
    ambiguous remote state is durable and is never retried automatically.
    """
    resolved_item_id = str(item_id or "").strip()
    resolved_source = str(source or "").strip()
    resolved_source_url = str(source_url or "").strip()
    resolved_title = str(title or "").strip()
    resolved_body = str(body or "").strip()
    if not resolved_item_id:
        raise ValueError("missing_item_id")
    if not resolved_source or not resolved_source_url:
        raise ValueError("missing_source")
    if not resolved_title:
        raise ValueError("missing_title")

    current_time = _utc(now)
    stamp = current_time.isoformat()
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    story_id = _manual_story_id(resolved_item_id, resolved_source_url)
    store = NewsroomV3Store(directory / "newsroom_v3.sqlite3")
    try:
        existing = store.get_story(story_id)
        if existing is not None:
            if existing.publish_state == "published" and existing.telegram_message_id is not None:
                return {
                    "status": "reconciled",
                    "story_id": story_id,
                    "telegram_message_id": existing.telegram_message_id,
                    "error": "",
                }
            if str(existing.last_publish_error or "").startswith(AMBIGUOUS_ERROR_PREFIX):
                _update_status(
                    directory,
                    last_manual_publish_state="ambiguous",
                    last_manual_story_id=story_id,
                    last_manual_publish_error=existing.last_publish_error,
                )
                return {
                    "status": "ambiguous",
                    "story_id": story_id,
                    "telegram_message_id": None,
                    "error": existing.last_publish_error,
                }
            if existing.publish_state == "publishing":
                return {
                    "status": "processing",
                    "story_id": story_id,
                    "telegram_message_id": None,
                    "error": "",
                }

        store.upsert_story(
            story_id=story_id,
            source_item_id=str(news_key or resolved_item_id).strip(),
            source=resolved_source,
            source_url=resolved_source_url,
            title=resolved_title,
            summary=resolved_body,
            published_at=str(published_at or stamp).strip(),
            fetched_at=stamp,
            media=[],
            source_priority="manual",
            fingerprint=_fingerprint(resolved_source_url, resolved_title, resolved_body),
            decision_state="ready",
            decision_reason="manual_editor_approved",
        )

        # Persist the attempt gate before the external call. If the process is
        # interrupted after Telegram sees a request, the next automatic cycle is
        # still suppressed and the SQLite story remains in a guarded state.
        _update_status(
            directory,
            last_publish_attempt_at=stamp,
            last_manual_publish_at=stamp,
            last_manual_publish_state="processing",
            last_manual_story_id=story_id,
            last_manual_publish_error="",
        )

        active_publisher = publisher if publisher is not None else build_production_publisher()
        result = NewsroomV3PublisherWorker(store, active_publisher).publish_story(story_id)

        if result.state == "published" and result.telegram_message_id is not None:
            _update_status(
                directory,
                last_published_at=stamp,
                last_published_story_id=story_id,
                last_telegram_message_id=result.telegram_message_id,
                last_manual_publish_at=stamp,
                last_manual_publish_state="succeeded",
                last_manual_story_id=story_id,
                last_manual_telegram_message_id=result.telegram_message_id,
                last_manual_publish_error="",
            )
            return {
                "status": "succeeded",
                "story_id": story_id,
                "telegram_message_id": result.telegram_message_id,
                "error": "",
            }

        if result.state == "already_published" and result.telegram_message_id is not None:
            return {
                "status": "reconciled",
                "story_id": story_id,
                "telegram_message_id": result.telegram_message_id,
                "error": "",
            }

        status = "ambiguous" if result.ambiguous else ("processing" if result.state == "busy" else "failed")
        _update_status(
            directory,
            last_manual_publish_at=stamp,
            last_manual_publish_state=status,
            last_manual_story_id=story_id,
            last_manual_publish_error=str(result.error or ""),
        )
        return {
            "status": status,
            "story_id": story_id,
            "telegram_message_id": result.telegram_message_id,
            "error": str(result.error or ""),
        }
    finally:
        store.close()
