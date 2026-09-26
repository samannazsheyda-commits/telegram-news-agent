from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .newsroom_v5_db import transaction
from .newsroom_v5_jobs import enqueue_once, retry_delay_seconds
from .newsroom_v5_store import NewsroomV5Store
from .services import has_persian


class AmbiguousPublishError(RuntimeError):
    """Raised when Telegram may have accepted a send but the response is uncertain."""


def prepare_publication(
    store: NewsroomV5Store,
    story_id: str,
    *,
    idempotency_key: str,
    copy_mode: str = "machine",
    title_fa: str | None = None,
    body_fa: str | None = None,
) -> dict:
    existing = store.get_publication_by_key(idempotency_key)
    if existing is not None:
        return existing

    story = store.get_story(story_id)
    if story is None:
        raise KeyError(story_id)
    if story.get("state") not in {"review", "editorial_ready"}:
        raise ValueError("story is not publishable")

    frozen_title = str(title_fa if title_fa is not None else story.get("title_fa") or "").strip()
    frozen_body = str(body_fa if body_fa is not None else story.get("body_fa") or "").strip()
    if not frozen_title or not has_persian(frozen_title):
        raise ValueError("valid Persian title is required")

    with transaction(store.conn):
        publication = store.create_publication_once(
            story_id,
            idempotency_key=idempotency_key,
            copy_mode=copy_mode,
            title_fa=frozen_title,
            body_fa=frozen_body,
            status="pending",
        )
        transitioned = store.transition_story(story_id, {"review", "editorial_ready"}, "publishing")
        if not transitioned:
            raise ValueError("story is not publishable")
        enqueue_once(
            store,
            "publish_story",
            story_id=story_id,
            payload={"publication_id": publication["id"]},
            key=f"publish:{publication['id']}",
        )
        store.append_audit(
            "publication_prepared",
            entity_type="publication",
            entity_id=publication["id"],
            detail={"story_id": story_id, "copy_mode": copy_mode},
        )
    return store.get_publication(publication["id"]) or publication


def _emit(event_sink, event_type: str, payload: dict) -> None:
    if event_sink is None:
        return
    event_sink(event_type, payload)


def _mark_published(store: NewsroomV5Store, publication: dict, message_id: Any, *, event_sink=None) -> dict:
    published_at = datetime.now(timezone.utc).isoformat()
    with transaction(store.conn):
        updated = store.update_publication(
            publication["id"],
            status="published",
            telegram_message_id=str(message_id),
            last_error=None,
            published_at=published_at,
        ) or publication
        store.transition_story(str(publication["story_id"]), {"publishing", "editorial_ready", "review"}, "published")
        store.append_audit(
            "publication_succeeded",
            entity_type="publication",
            entity_id=publication["id"],
            detail={"story_id": publication["story_id"], "telegram_message_id": str(message_id)},
        )
    payload = {
        "story_id": str(publication["story_id"]),
        "publication_id": str(publication["id"]),
        "telegram_message_id": str(message_id),
        "published_at": published_at,
    }
    _emit(event_sink, "story_published", payload)
    _emit(event_sink, "counts_changed", {"reason": "story_published", "story_id": str(publication["story_id"])})
    result = dict(updated)
    result["status"] = "published"
    return result


def process_publication(
    store: NewsroomV5Store,
    publication_id: str,
    *,
    sender: Callable[[str, str], Any],
    reconciler: Callable[[dict], dict | None] | None = None,
    event_sink: Callable[[str, dict], Any] | None = None,
) -> dict:
    publication = store.get_publication(publication_id)
    if publication is None:
        raise KeyError(publication_id)
    if publication.get("status") == "published":
        return publication

    if publication.get("status") == "reconcile":
        # Telegram may already hold this post. Only an explicit reconciliation
        # answer may lead to a send; without one the post waits for an operator.
        reconciliation: dict = {}
        if reconciler is not None:
            try:
                reconciliation = reconciler(dict(publication)) or {}
            except Exception as exc:
                reconciliation = {"found": False, "error": str(exc)}
        if reconciliation.get("found") and reconciliation.get("telegram_message_id") is not None:
            return _mark_published(
                store,
                publication,
                reconciliation["telegram_message_id"],
                event_sink=event_sink,
            )
        if reconciliation.get("confirmed_absent"):
            attempts = int(publication.get("attempt_count") or 0) + 1
            store.update_publication(publication_id, status="retry", attempt_count=attempts, last_error="confirmed_absent")
            enqueue_once(
                store,
                "publish_story",
                story_id=str(publication["story_id"]),
                payload={"publication_id": publication_id},
                key=f"publish:{publication_id}:resend:{attempts}",
            )
            result = dict(store.get_publication(publication_id) or publication)
            result["status"] = "retry"
            return result
        enqueue_once(
            store,
            "reconcile_publication",
            story_id=str(publication["story_id"]),
            payload={"publication_id": publication_id},
            key=f"reconcile:{publication_id}",
        )
        result = dict(publication)
        result["status"] = "reconcile"
        return result

    try:
        message_id = sender(str(publication.get("title_fa") or ""), str(publication.get("body_fa") or ""))
    except AmbiguousPublishError as exc:
        store.update_publication(publication_id, status="reconcile", last_error=str(exc))
        enqueue_once(
            store,
            "reconcile_publication",
            story_id=str(publication["story_id"]),
            payload={"publication_id": publication_id},
            key=f"reconcile:{publication_id}",
        )
        result = dict(store.get_publication(publication_id) or publication)
        result["status"] = "reconcile"
        return result
    except Exception as exc:
        attempts = int(publication.get("attempt_count") or 0) + 1
        store.update_publication(publication_id, status="retry", attempt_count=attempts, last_error=str(exc))
        job = enqueue_once(
            store,
            "publish_story",
            story_id=str(publication["story_id"]),
            payload={"publication_id": publication_id},
            key=f"publish:{publication_id}",
        )
        store.retry_job(job["id"], error=str(exc), delay_seconds=retry_delay_seconds(attempts, seed=publication_id))
        result = dict(store.get_publication(publication_id) or publication)
        result["status"] = "retry"
        return result

    return _mark_published(store, publication, message_id, event_sink=event_sink)
