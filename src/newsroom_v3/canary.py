from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..event_ledger import EventLedger
from ..newsroom_channel_publisher import build_channel_copy_publisher
from ..newsroom_eligibility import _fresh_enough, _parse_published
from .outbox import NewsroomV3PublisherWorker
from .publisher_adapter import V3TelegramPublisherAdapter
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


def _v2_published_index(ledger: EventLedger) -> tuple[set[str], set[str], set[str]]:
    urls: set[str] = set()
    item_ids: set[str] = set()
    fingerprints: set[str] = set()
    for record in ledger.records():
        if not list(record.published_message_ids or []):
            continue
        for value in record.source_variants or []:
            url = str(value or "").strip()
            if url:
                urls.add(url)
        data = record.fingerprint_data or {}
        item_id = str(data.get("source_item_id") or "").strip()
        if item_id:
            item_ids.add(item_id)
        fingerprint = str(record.fingerprint or "").strip()
        if fingerprint:
            fingerprints.add(fingerprint)
    return urls, item_ids, fingerprints


def _published_by_index(story: StoryRecord, index: tuple[set[str], set[str], set[str]]) -> bool:
    urls, item_ids, fingerprints = index
    source_url = str(story.source_url or "").strip()
    source_item_id = str(story.source_item_id or "").strip()
    fingerprint = str(story.fingerprint or "").strip()
    if source_url and source_url in urls:
        return True
    if source_item_id and source_item_id in item_ids:
        return True
    if fingerprint and fingerprint in fingerprints:
        return True
    return False


def _published_by_v2(story: StoryRecord, ledger: EventLedger) -> bool:
    return _published_by_index(story, _v2_published_index(ledger))


def _published_time(story: StoryRecord) -> datetime:
    published = _parse_published(story.published_at)
    return published or datetime.min.replace(tzinfo=timezone.utc)


def _still_fresh(story: StoryRecord, *, now: datetime) -> bool:
    published = _parse_published(story.published_at)
    if published is None:
        return False
    return _fresh_enough(published, now)


def iter_publishable_stories(store: NewsroomV3Store, *, max_rows: int = 2000):
    """Walk ready stories past the first page so stale backlog cannot hide fresh news."""
    offset = 0
    page = 100
    limit = max(1, int(max_rows))
    while offset < limit:
        batch = store.list_publishable(limit=min(page, limit - offset), offset=offset)
        if not batch:
            break
        yield from batch
        offset += len(batch)
        if len(batch) < page:
            break


def list_safe_candidates(
    store: NewsroomV3Store,
    ledger: EventLedger | None,
    *,
    now: datetime,
) -> list[StoryRecord]:
    published = (
        _v2_published_index(ledger)
        if ledger is not None
        else (set(), set(), set())
    )
    found: list[StoryRecord] = []
    for story in iter_publishable_stories(store, max_rows=400):
        if ledger is not None and _published_by_index(story, published):
            continue
        if not _still_fresh(story, now=now):
            continue
        found.append(story)
        if len(found) >= 8:
            break
    return sorted(found, key=_published_time, reverse=True)


def _safe_candidate(
    store: NewsroomV3Store,
    ledger: EventLedger,
    *,
    now: datetime | None = None,
) -> StoryRecord | None:
    resolved_now = now or datetime.now(timezone.utc)
    candidates = list_safe_candidates(store, ledger, now=resolved_now)
    return candidates[0] if candidates else None


def canary_preflight(*, data_dir: str | Path) -> dict:
    """Read-only gate used before briefly stopping V2 for the real canary."""
    directory = Path(data_dir)
    marker_path = directory / CANARY_MARKER
    if marker_path.exists():
        return {"ready": False, "reason": "already_attempted"}
    if not _shadow_is_healthy(_read_json(directory / SHADOW_STATUS)):
        return {"ready": False, "reason": "shadow_not_healthy"}
    store_path = directory / "newsroom_v3.sqlite3"
    if not store_path.exists():
        return {"ready": False, "reason": "store_missing"}

    store = NewsroomV3Store(store_path)
    try:
        story = _safe_candidate(store, EventLedger(directory / V2_LEDGER))
        if story is None:
            return {"ready": False, "reason": "no_safe_candidate"}
        return {
            "ready": True,
            "reason": "safe_candidate",
            "story_id": story.story_id,
            "source": story.source,
            "source_url": story.source_url,
        }
    finally:
        store.close()


def build_production_publisher() -> V3TelegramPublisherAdapter:
    """Wrap the shared Luna-required channel publisher for V3 outbox writes."""
    return V3TelegramPublisherAdapter(build_channel_copy_publisher())


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
        safe_story = _safe_candidate(store, EventLedger(directory / V2_LEDGER))
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Newsroom V3 guarded one-shot canary")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--confirm-one-shot", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()

    if args.preflight:
        result = canary_preflight(data_dir=args.data_dir)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("ready") is True else 3

    if not args.confirm_one_shot:
        parser.error("--confirm-one-shot is required")
    result = run_one_shot_canary(
        data_dir=args.data_dir,
        publisher=build_production_publisher(),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
