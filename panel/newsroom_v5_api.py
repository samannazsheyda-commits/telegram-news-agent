from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, abort, current_app, jsonify, request

from panel.app import login_required
from src.newsroom_v5_identity import reject_story
from src.newsroom_v5_publish import prepare_publication
from src.services import has_persian


bp = Blueprint("newsroom_v5", __name__, url_prefix="/api/v5")


def _store():
    store = current_app.extensions.get("newsroom_v5_store")
    if store is None:
        abort(503, description="Newsroom V5 runtime store is not enabled")
    return store


def _events():
    return current_app.extensions.get("newsroom_v5_events")


def _emit(event_type: str, payload: dict) -> None:
    broker = _events()
    if broker is not None:
        broker.publish(event_type, payload)


def _confirmed() -> bool:
    payload = request.get_json(silent=True) or {}
    return payload.get("confirmed") is True


def _age_seconds(value: str | None) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0, int((datetime.now(timezone.utc) - published.astimezone(timezone.utc)).total_seconds()))


def _review_item(row: dict) -> dict:
    story_id = str(row["id"])
    return {
        "id": story_id,
        "source_id": row.get("source_id"),
        "source_name": row.get("source_name") or row.get("source_id") or "منبع",
        "source_url": row.get("source_url"),
        "published_at_source": row.get("published_at_source"),
        "age_seconds": _age_seconds(row.get("published_at_source")),
        "title_fa": row.get("title_fa") or "",
        "body_fa": row.get("body_fa") or "",
        "importance": row.get("importance"),
        "priority_class": row.get("priority_class"),
        "editorial_reason": row.get("editorial_reason"),
        "confidence": row.get("confidence"),
        "actions": {
            "detail": f"/api/v5/story/{story_id}",
            "publish": f"/api/v5/story/{story_id}/publish",
            "reject": f"/api/v5/story/{story_id}/reject",
            "copy": f"/api/v5/story/{story_id}/copy",
            "luna_context": f"/api/v5/luna/context/story/{story_id}",
        },
    }


@bp.get("/review")
@login_required
def review_list():
    limit = request.args.get("limit", 25, type=int) or 25
    cursor = request.args.get("cursor") or None
    try:
        page = _store().list_review(limit=limit, cursor=cursor)
    except ValueError:
        return jsonify({"error": "invalid_cursor"}), 400
    return jsonify({
        "items": [_review_item(dict(row)) for row in page["items"]],
        "next_cursor": page["next_cursor"],
    })


@bp.get("/story/<story_id>")
@login_required
def story_detail(story_id: str):
    story = _store().get_story(story_id)
    if story is None:
        abort(404)
    payload = dict(story)
    payload["age_seconds"] = _age_seconds(payload.get("published_at_source"))
    return jsonify(payload)


@bp.patch("/story/<story_id>/copy")
@login_required
def edit_copy(story_id: str):
    store = _store()
    story = store.get_story(story_id)
    if story is None:
        abort(404)
    if story.get("state") not in {"review", "editorial_ready"}:
        return jsonify({"error": "story_not_editable", "state": story.get("state")}), 409
    payload = request.get_json(silent=True) or {}
    title_fa = str(payload.get("title_fa") or "").strip()
    body_fa = str(payload.get("body_fa") or "").strip()
    if not title_fa or not has_persian(title_fa):
        return jsonify({"error": "persian_title_required"}), 400
    updated = store.set_translation(
        story_id,
        title_fa=title_fa,
        body_fa=body_fa,
        backend="manual",
        quality_passed=True,
        last_error=None,
    )
    store.append_audit(
        "story_copy_edited",
        actor="operator",
        entity_type="story",
        entity_id=story_id,
        detail={"copy_mode": "manual"},
    )
    _emit("story_updated", {"story_id": story_id, "state": updated.get("state")})
    return jsonify(_review_item(updated))


@bp.post("/story/<story_id>/reject")
@login_required
def reject(story_id: str):
    if not _confirmed():
        return jsonify({"error": "confirmation_required", "story_id": story_id}), 400
    store = _store()
    try:
        story = reject_story(store, story_id, actor="operator")
    except KeyError:
        abort(404)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    _emit("story_rejected", {"story_id": story_id})
    _emit("counts_changed", _counts(store))
    return jsonify({"ok": True, "story_id": story_id, "state": story.get("state")})


@bp.post("/story/<story_id>/publish")
@login_required
def publish(story_id: str):
    if not _confirmed():
        return jsonify({"error": "confirmation_required", "story_id": story_id}), 400
    store = _store()
    payload = request.get_json(silent=True) or {}
    key = str(request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or "").strip()
    if not key:
        # A client-generated key is preferred; this server fallback is unique to
        # the request and still preserves DB-level one-send semantics.
        key = f"manual:{story_id}:{uuid4().hex}"
    try:
        publication = prepare_publication(
            store,
            story_id,
            idempotency_key=key,
            copy_mode="manual" if payload.get("title_fa") is not None else "machine",
            title_fa=payload.get("title_fa"),
            body_fa=payload.get("body_fa"),
        )
    except KeyError:
        abort(404)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    _emit("story_updated", {"story_id": story_id, "state": "publishing"})
    _emit("counts_changed", _counts(store))
    return jsonify({
        "ok": True,
        "story_id": story_id,
        "state": "publishing",
        "publication_id": publication["id"],
        "idempotency_key": publication["idempotency_key"],
    }), 202


def _counts(store) -> dict:
    rows = store.conn.execute("SELECT state, COUNT(*) AS count FROM stories GROUP BY state").fetchall()
    counts = {str(row["state"]): int(row["count"]) for row in rows}
    return {
        "review": counts.get("review", 0),
        "publishing": counts.get("publishing", 0),
        "published": counts.get("published", 0),
        "rejected": counts.get("rejected", 0),
        "failed": counts.get("failed", 0),
    }


@bp.get("/counts")
@login_required
def counts():
    return jsonify(_counts(_store()))


@bp.get("/health")
@login_required
def health():
    store = _store()
    conn = store.conn
    now = datetime.now(timezone.utc)
    jobs: dict[str, dict] = {}
    for kind in ("translate_story", "editorial_story", "publish_story", "reconcile_publication"):
        rows = conn.execute("SELECT status, COUNT(*) FROM jobs WHERE kind=? GROUP BY status", (kind,)).fetchall()
        by_status = {str(row[0]): int(row[1]) for row in rows}
        oldest = conn.execute(
            "SELECT MIN(created_at) FROM jobs WHERE kind=? AND status IN ('pending','running')", (kind,)
        ).fetchone()[0]
        jobs[kind] = {
            "pending": by_status.get("pending", 0),
            "running": by_status.get("running", 0),
            "failed": by_status.get("failed", 0),
            "oldest_pending_age_seconds": _age_seconds(oldest),
        }
    publications = {
        str(row[0]): int(row[1])
        for row in conn.execute("SELECT status, COUNT(*) FROM publications GROUP BY status").fetchall()
    }
    states = _counts(store)
    received = conn.execute("SELECT COUNT(*) FROM stories WHERE state='received'").fetchone()[0]
    last = {
        "story_discovered": conn.execute("SELECT MAX(created_at) FROM stories").fetchone()[0],
        "translation": conn.execute("SELECT MAX(translated_at) FROM translations WHERE quality_passed=1").fetchone()[0],
        "editorial": conn.execute("SELECT MAX(decided_at) FROM editorial_decisions").fetchone()[0],
        "publication": conn.execute("SELECT MAX(published_at) FROM publications WHERE status='published'").fetchone()[0],
    }
    attention = bool(
        publications.get("reconcile", 0)
        or any(item["failed"] for item in jobs.values())
        or states.get("failed", 0)
    )
    schema = conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
    return jsonify({
        "checked_at": now.isoformat(),
        "schema_version": int(schema[0]) if schema else None,
        "store_backend": current_app.config.get("NEWSROOM_STORE_BACKEND"),
        "auto_publish_enabled": bool(current_app.config.get("NEWSROOM_AUTO_PUBLISH_ENABLED")),
        "stories": {**states, "awaiting_translation": int(received)},
        "jobs": jobs,
        "publications": {
            "pending": publications.get("pending", 0),
            "retry": publications.get("retry", 0),
            "reconcile": publications.get("reconcile", 0),
            "published": publications.get("published", 0),
        },
        "last": last,
        "attention_required": attention,
    })


@bp.get("/published")
@login_required
def published_list():
    limit = request.args.get("limit", 25, type=int) or 25
    cursor = request.args.get("cursor") or None
    try:
        page = _store().list_published(limit=limit, cursor=cursor)
    except ValueError:
        return jsonify({"error": "invalid_cursor"}), 400
    return jsonify({"items": [dict(row) for row in page["items"]], "next_cursor": page["next_cursor"]})
