from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..event_ledger import EventLedger
from .outbox import NewsroomV3PublisherWorker
from .store import NewsroomV3Store, StoryRecord


CANARY_MARKER = "newsroom_v3_canary_once.json"
SHADOW_STATUS = "newsroom_v3_shadow_status.json"
V2_LEDGER = "event_ledger.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _shadow_is_healthy(status: dict) -> bool:
    return bool(
        status.get("mode") == "shadow"
        and int(status.get("telegram_writes") or 0) == 0
        and int(status.get("sources_ok") or 0) >= 1
        and int(status.get("processed") or 0) >= 1
        and int(status.get("ready") or 0) >= 1
    )


def _published_by_v2(story: StoryRecord, ledger: EventLedger) -> bool:
    source_url = str(story.source_url or "").strip()
    source_item_id = str(story.source_item_id or "").strip()
    fingerprint = str(story.fingerprint or "").strip()
    for record in ledger.records():
        if not list(record.published_message_ids or []):
            continue
        variants = {str(value or "").strip() for value in (record.source_variants or [])}
        data = record.fingerprint_data or {}
        old_source_item_id = str(data.get("source_item_id") or "").strip()
        if source_url and source_url in variants:
            return True
        if source_item_id and old_source_item_id and source_item_id == old_source_item_id:
            return True
        if fingerprint and str(record.fingerprint or "").strip() == fingerprint:
            return True
    return False


def run_one_shot_canary(
    *,
    data_dir: str | Path,
    publisher: Callable[[StoryRecord], object] | None,
) -> dict:
    """Attempt at most one V3 Telegram publication after verified shadow evidence.

    The one-shot marker is persisted *before* invoking the external publisher so
    an ambiguous network response or process crash can never cause an automatic
    second canary attempt.
    """
    if publisher is None:
        raise ValueError("publisher is required for V3 canary")

    directory = Path(data_dir)
    marker_path = directory / CANARY_MARKER
    if marker_path.exists():
        prior = _read_json(marker_path)
        return {
            "state": "already_attempted",
            "story_id": str(prior.get("story_id") or ""),
            "telegram_writes": 0,
            "previous_state": str(prior.get("state") or ""),
        }

    shadow_status = _read_json(directory / SHADOW_STATUS)
    if not _shadow_is_healthy(shadow_status):
        return {"state": "shadow_not_healthy", "telegram_writes": 0}

    store_path = directory / "newsroom_v3.sqlite3"
    if not store_path.exists():
        return {"state": "no_candidate", "telegram_writes": 0}

    store = NewsroomV3Store(store_path)
    try:
        ledger = EventLedger(directory / V2_LEDGER)
        safe_story = None
        for story in store.list_publishable(limit=100):
            if _published_by_v2(story, ledger):
                continue
            safe_story = story
            break

        if safe_story is None:
            return {"state": "no_candidate", "telegram_writes": 0}

        attempt_marker = {
            "state": "attempting",
            "story_id": safe_story.story_id,
            "source": safe_story.source,
            "source_url": safe_story.source_url,
            "attempted_at": _utc_now(),
            "telegram_writes": 0,
        }
        _atomic_json(marker_path, attempt_marker)

        result = NewsroomV3PublisherWorker(store, publisher).publish_story(safe_story.story_id)
        published = result.state == "published" and result.telegram_message_id is not None
        final_marker = {
            **attempt_marker,
            "state": result.state,
            "finished_at": _utc_now(),
            "attempt_no": result.attempt_no,
            "error": result.error,
            "telegram_message_id": result.telegram_message_id,
            "telegram_writes": 1 if published else 0,
        }
        _atomic_json(marker_path, final_marker)
        return final_marker
    finally:
        store.close()
