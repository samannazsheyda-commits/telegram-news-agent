from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..event_ledger import EventLedger
from ..newsroom_raw_intake import build_raw_fetchers
from .canary import (
    CANARY_MARKER,
    V2_LEDGER,
    _published_by_v2,
    _published_time,
    _still_fresh,
    build_production_publisher,
)
from .final_gate import FinalGateDecision, LunaFinalPublishGate
from .outbox import AMBIGUOUS_ERROR_PREFIX, NewsroomV3PublisherWorker
from .publication_policy import count_successful_publications, list_recent_published
from .shadow import NewsroomV3ShadowPipeline
from .store import NewsroomV3Store, StoryRecord


PRODUCTION_STATE = "newsroom_v3_production_status.json"
_cached_publisher = None
_TRANSIENT_GATE_REASONS = {"luna_unavailable", "luna_error", "invalid_luna_decision"}


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


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _production_publisher():
    global _cached_publisher
    if _cached_publisher is None:
        _cached_publisher = build_production_publisher()
    return _cached_publisher


def cutover_gate(*, data_dir: str | Path) -> dict:
    """Allow V3 primary mode only after exactly one verified canary publish."""
    marker_path = Path(data_dir) / CANARY_MARKER
    if not marker_path.exists():
        return {"ready": False, "reason": "canary_missing"}
    marker = _read_json(marker_path)
    if not marker:
        return {"ready": False, "reason": "canary_unreadable"}
    if str(marker.get("state") or "") != "published":
        return {"ready": False, "reason": "canary_not_published"}
    if int(marker.get("attempt_no") or 0) != 1:
        return {"ready": False, "reason": "canary_attempt_count_invalid"}
    if int(marker.get("telegram_writes") or 0) != 1:
        return {"ready": False, "reason": "canary_write_count_invalid"}
    message_id = marker.get("telegram_message_id")
    if not isinstance(message_id, int):
        return {"ready": False, "reason": "canary_message_id_missing"}
    return {
        "ready": True,
        "reason": "verified_canary",
        "telegram_message_id": message_id,
        "story_id": str(marker.get("story_id") or ""),
    }


def _collect(fetchers) -> tuple[list, int, int]:
    items = []
    sources_ok = 0
    sources_failed = 0
    for fetcher in list(fetchers or []):
        try:
            items.extend(list(fetcher() or []))
            sources_ok += 1
        except Exception:
            sources_failed += 1
    return items, sources_ok, sources_failed


def _safe_candidates(
    store: NewsroomV3Store,
    ledger: EventLedger,
    *,
    now: datetime,
) -> list[StoryRecord]:
    candidates = [
        story
        for story in store.list_publishable(limit=100)
        if not _published_by_v2(story, ledger) and _still_fresh(story, now=now)
    ]
    return sorted(candidates, key=_published_time, reverse=True)


def _candidate_for_publish(
    store: NewsroomV3Store,
    ledger: EventLedger,
    *,
    now: datetime,
    retry_cooldown_seconds: int,
    max_attempts: int,
) -> tuple[StoryRecord | None, str]:
    candidates = _safe_candidates(store, ledger, now=now)
    if not candidates:
        return None, "no_safe_candidate"

    saw_ambiguous = False
    saw_cooldown = False
    saw_attempt_limit = False
    for story in candidates:
        if str(story.last_publish_error or "").startswith(AMBIGUOUS_ERROR_PREFIX):
            saw_ambiguous = True
            continue
        attempts = store.list_publish_attempts(story.story_id)
        if len(attempts) >= max(1, int(max_attempts)):
            saw_attempt_limit = True
            continue
        if attempts:
            last = attempts[-1]
            finished = _parse_time(last.finished_at)
            if (
                last.state == "failed"
                and finished is not None
                and (now - finished).total_seconds() < max(0, int(retry_cooldown_seconds))
            ):
                saw_cooldown = True
                continue
        return story, "safe_candidate"

    if saw_ambiguous:
        return None, "ambiguous_remote_state"
    if saw_cooldown:
        return None, "retry_cooldown"
    if saw_attempt_limit:
        return None, "attempt_limit"
    return None, "no_safe_candidate"


def _within_publish_interval(
    state: dict,
    *,
    now: datetime,
    min_publish_interval_seconds: int,
) -> bool:
    timestamps = [
        parsed
        for parsed in (
            _parse_time(state.get("last_published_at")),
            _parse_time(state.get("last_publish_attempt_at")),
        )
        if parsed is not None
    ]
    if not timestamps:
        return False
    previous = max(timestamps)
    return (now - previous).total_seconds() < max(0, int(min_publish_interval_seconds))


def _persist_result(status_path: Path, prior_status: dict, result: dict) -> dict:
    _atomic_json(status_path, {**prior_status, **result})
    return result


def run_once(
    *,
    data_dir: str | Path = "data",
    fetchers=None,
    publisher: Callable[[StoryRecord], object] | None = None,
    final_gate: Callable[[StoryRecord, list[StoryRecord]], FinalGateDecision] | None = None,
    now: datetime | None = None,
    publish_enabled: bool = True,
    min_publish_interval_seconds: int | None = None,
    retry_cooldown_seconds: int | None = None,
    max_attempts: int | None = None,
    daily_limit: int | None = None,
) -> dict:
    """Run one guarded V3 production cycle with at most one Telegram write."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)

    interval = (
        int(os.environ.get("NEWSROOM_V3_MIN_PUBLISH_INTERVAL_SECONDS", "60"))
        if min_publish_interval_seconds is None
        else int(min_publish_interval_seconds)
    )
    cooldown = (
        int(os.environ.get("NEWSROOM_V3_RETRY_COOLDOWN_SECONDS", "300"))
        if retry_cooldown_seconds is None
        else int(retry_cooldown_seconds)
    )
    attempts_limit = (
        int(os.environ.get("NEWSROOM_V3_MAX_PUBLISH_ATTEMPTS", "3"))
        if max_attempts is None
        else int(max_attempts)
    )
    resolved_daily_limit = (
        int(os.environ.get("NEWSROOM_V3_DAILY_LIMIT", "25"))
        if daily_limit is None
        else int(daily_limit)
    )
    resolved_daily_limit = max(1, resolved_daily_limit)

    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    status_path = directory / PRODUCTION_STATE
    prior_status = _read_json(status_path)
    store = NewsroomV3Store(directory / "newsroom_v3.sqlite3")
    try:
        resolved_fetchers = build_raw_fetchers() if fetchers is None else fetchers
        items, sources_ok, sources_failed = _collect(resolved_fetchers)
        shadow_result = NewsroomV3ShadowPipeline(store).run(items, now=current_time)
        daily_published = count_successful_publications(store, now=current_time)

        base = {
            "mode": "production",
            "sources_ok": sources_ok,
            "sources_failed": sources_failed,
            "items_fetched": len(items),
            "processed": shadow_result.processed,
            "ready": shadow_result.ready,
            "waiting": shadow_result.waiting,
            "rejected": shadow_result.rejected,
            "duplicates": shadow_result.duplicates,
            "published": 0,
            "telegram_writes": 0,
            "publish_failed": 0,
            "final_gate_rejected": 0,
            "story_id": "",
            "telegram_message_id": None,
            "daily_published": daily_published,
            "daily_limit": resolved_daily_limit,
            "daily_remaining": max(0, resolved_daily_limit - daily_published),
            "reason": "",
            "error": "",
            "last_cycle_at": current_time.isoformat(),
        }

        if not publish_enabled:
            return _persist_result(status_path, prior_status, {**base, "reason": "publish_paused"})

        if daily_published >= resolved_daily_limit:
            return _persist_result(status_path, prior_status, {**base, "reason": "daily_limit"})

        if _within_publish_interval(
            prior_status,
            now=current_time,
            min_publish_interval_seconds=interval,
        ):
            return _persist_result(status_path, prior_status, {**base, "reason": "publish_interval"})

        story, reason = _candidate_for_publish(
            store,
            EventLedger(directory / V2_LEDGER),
            now=current_time,
            retry_cooldown_seconds=cooldown,
            max_attempts=attempts_limit,
        )
        if story is None:
            return _persist_result(status_path, prior_status, {**base, "reason": reason})

        active_gate = final_gate
        if active_gate is None and publisher is None:
            active_gate = LunaFinalPublishGate()
        if active_gate is not None:
            recent = list_recent_published(store, limit=25)
            try:
                decision = active_gate(story, recent)
            except Exception as exc:
                return _persist_result(
                    status_path,
                    prior_status,
                    {
                        **base,
                        "story_id": story.story_id,
                        "reason": "final_gate_error",
                        "error": f"{type(exc).__name__}",
                    },
                )
            if not isinstance(decision, FinalGateDecision):
                return _persist_result(
                    status_path,
                    prior_status,
                    {
                        **base,
                        "story_id": story.story_id,
                        "reason": "final_gate_error",
                        "error": "invalid_final_gate_contract",
                    },
                )
            if not decision.approved:
                gate_reason = str(decision.reason or "rejected").strip() or "rejected"
                if gate_reason in _TRANSIENT_GATE_REASONS:
                    return _persist_result(
                        status_path,
                        prior_status,
                        {
                            **base,
                            "story_id": story.story_id,
                            "reason": "final_gate_error",
                            "error": gate_reason,
                        },
                    )
                store.set_decision(story.story_id, "rejected", reason=f"final_gate:{gate_reason}")
                return _persist_result(
                    status_path,
                    prior_status,
                    {
                        **base,
                        "story_id": story.story_id,
                        "final_gate_rejected": 1,
                        "reason": "final_gate_rejected",
                        "error": gate_reason,
                    },
                )

        active_publisher = publisher if publisher is not None else _production_publisher()
        publish_result = NewsroomV3PublisherWorker(store, active_publisher).publish_story(story.story_id)
        if publish_result.state == "published" and publish_result.telegram_message_id is not None:
            next_daily_count = daily_published + 1
            result = {
                **base,
                "published": 1,
                "telegram_writes": 1,
                "story_id": story.story_id,
                "telegram_message_id": publish_result.telegram_message_id,
                "daily_published": next_daily_count,
                "daily_remaining": max(0, resolved_daily_limit - next_daily_count),
                "reason": "published",
            }
            _atomic_json(
                status_path,
                {
                    **prior_status,
                    **result,
                    "last_published_at": current_time.isoformat(),
                    "last_published_story_id": story.story_id,
                    "last_telegram_message_id": publish_result.telegram_message_id,
                },
            )
            return result

        result = {
            **base,
            "publish_failed": 1 if publish_result.state == "failed" else 0,
            "story_id": story.story_id,
            "reason": (
                "ambiguous_remote_state"
                if publish_result.ambiguous
                else publish_result.state
            ),
            "error": publish_result.error,
        }
        return _persist_result(status_path, prior_status, result)
    finally:
        store.close()
