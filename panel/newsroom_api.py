from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request, session

from src.formatters import _source_label

from .command_center import (
    _enqueue,
    _find_live_item,
    _normalise_priorities,
    _public_settings,
    _remove_from_queue,
    _remove_live_ids,
    _review_record_from_live,
    _settings,
    _upsert_history,
    _write_list,
)


bp = Blueprint("newsroom_api", __name__)
_TERMINAL_LIVE_STATUSES = {"auto_published", "published_auto", "published_manual"}


def _data():
    return current_app.extensions["editorial_data"]


def _read(path: str, default):
    value, _ = _data().read_json(path, default)
    return value


def _rows(path: str) -> list[dict]:
    value = _read(path, [])
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _story_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _has_persian(value: str) -> bool:
    return any("\u0600" <= char <= "\u06ff" for char in str(value or ""))


def _editor_copy(row: dict) -> tuple[str, str, tuple[dict, int] | None]:
    title = str(row.get("final_persian_title") or row.get("persian_title") or "").strip()
    body = str(row.get("final_persian_body") or row.get("persian_body") or "").strip()
    payload = request.get_json(silent=True)
    if payload is None:
        return title, body, None
    if not isinstance(payload, dict):
        return title, body, ({"ok": False, "status": "failed", "error": "invalid_editor_payload", "message": "متن ویرایش معتبر نیست"}, 400)
    if "title" in payload:
        title = str(payload.get("title") or "").strip()
    if "body" in payload:
        body = str(payload.get("body") or "").strip()
    if len(title) > 280 or len(body) > 4000:
        return title, body, ({"ok": False, "status": "failed", "error": "invalid_editor_payload", "message": "متن ویرایش از حد مجاز طولانی‌تر است"}, 400)
    return title, body, None


def _live_public(row: dict) -> dict:
    source = str(row.get("source") or "")
    return {
        "id": _story_id(row),
        "news_key": str(row.get("news_key") or ""),
        "title": str(row.get("final_persian_title") or row.get("persian_title") or row.get("display_title") or row.get("title") or ""),
        "body": str(row.get("final_persian_body") or row.get("persian_body") or ""),
        "source": _source_label(source) or "منبع",
        "source_url": str(row.get("source_url") or row.get("link") or ""),
        "status": str(row.get("panel_status") or "new"),
        "priority": str(row.get("source_priority") or row.get("priority") or "normal"),
        "discovered_at": str(row.get("updated_at") or row.get("discovered_at") or row.get("fetched_at") or ""),
    }


def _fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _normalize_result(payload: dict, *, default_status: str = "queued") -> dict:
    status = str(payload.get("status") or default_status)
    if status not in {"queued", "processing", "succeeded", "failed", "ambiguous", "reconciled"}:
        status = default_status
    result = {
        "ok": bool(payload.get("ok", status not in {"failed"})),
        "status": status,
        "command_id": str(payload.get("command_id") or ""),
        "message": str(payload.get("message") or ""),
        **({"review_url": payload["review_url"]} if payload.get("review_url") else {}),
    }
    if isinstance(payload.get("telegram_message_id"), int):
        result["telegram_message_id"] = payload["telegram_message_id"]
    return result


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.get("/api/newsroom/snapshot")
def snapshot():
    settings, _ = _settings()
    state = _read("state.json", {})
    state = state if isinstance(state, dict) else {}
    v3 = _read("data/newsroom_v3_production_status.json", {})
    v3 = v3 if isinstance(v3, dict) else {}
    live = _rows("data/panel_live_feed.json")
    queue = _rows("data/editorial_queue.json")
    history = _rows("data/editorial_history.json")

    engine = str(state.get("newsroom_engine") or os.environ.get("NEWSROOM_ENGINE") or "unknown").strip().lower()
    if engine not in {"v3", "v2", "v2_fallback"}:
        engine = "unknown"

    v3_public = {
        "mode": str(v3.get("mode") or ""),
        "reason": str(v3.get("reason") or ""),
        "error": str(v3.get("error") or ""),
        "last_cycle_at": str(v3.get("last_cycle_at") or state.get("last_cycle_at") or ""),
        "last_published_at": str(v3.get("last_published_at") or ""),
        "sources_ok": _safe_int(v3.get("sources_ok")),
        "sources_failed": _safe_int(v3.get("sources_failed")),
        "items_fetched": _safe_int(v3.get("items_fetched")),
        "processed": _safe_int(v3.get("processed")),
        "ready": _safe_int(v3.get("ready")),
        "waiting": _safe_int(v3.get("waiting")),
        "rejected": _safe_int(v3.get("rejected")),
        "duplicates": _safe_int(v3.get("duplicates")),
        "published": _safe_int(v3.get("published")),
        "telegram_writes": _safe_int(v3.get("telegram_writes")),
        "publish_failed": _safe_int(v3.get("publish_failed")),
        "story_id": str(v3.get("story_id") or ""),
        "telegram_message_id": v3.get("telegram_message_id") if isinstance(v3.get("telegram_message_id"), int) else None,
    }

    public_settings = _public_settings(settings)
    try:
        public_settings["priority_terms"] = _normalise_priorities(settings.get("priority_terms") or [])
    except ValueError:
        public_settings["priority_terms"] = []

    live_public = [_live_public(row) for row in live[:60]]
    snapshot_core = {
        "engine": engine,
        "agent_state": "active" if v3_public["last_cycle_at"] else "unknown",
        "telegram_state": str(state.get("telegram_state") or ("ok" if v3_public["telegram_writes"] else "unknown")),
        "publishing": bool(settings.get("auto_publish", True)) and not bool(settings.get("emergency_lock", False)),
        "emergency_lock": bool(settings.get("emergency_lock", False)),
        "v3": v3_public,
        "counts": {
            "live": len(live),
            "review": sum(1 for row in queue if str(row.get("status") or "pending") == "pending"),
            "published": sum(1 for row in history if str(row.get("status") or "") in {"published_auto", "published_manual"}),
            "rejected": sum(1 for row in history if str(row.get("status") or "") in {"rejected_manual", "superseded"}),
        },
        "live": live_public,
        "settings": public_settings,
    }
    return jsonify({"ok": True, **snapshot_core, "fingerprint": _fingerprint(snapshot_core), "snapshot_at": _now_iso()})


@bp.post("/api/newsroom/scan")
def scan():
    command_id = _enqueue("refresh")
    return jsonify({"ok": True, "status": "queued", "command_id": command_id, "message": "اسکن فوری در صف اجرا قرار گرفت"}), 202


@bp.post("/api/newsroom/publishing")
def publishing():
    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get("enabled"))

    def transform(value: dict) -> dict:
        value["auto_publish"] = enabled
        value["emergency_lock"] = not enabled
        return value

    from .command_center import _write_settings

    saved = _write_settings(transform)
    active = bool(saved.get("auto_publish")) and not bool(saved.get("emergency_lock"))
    return jsonify({"ok": True, "status": "succeeded", "command_id": "", "publishing": active, "message": "انتشار فعال شد" if active else "انتشار متوقف شد"})


@bp.post("/api/newsroom/live/<item_id>/review")
def review_live(item_id: str):
    row = _find_live_item(item_id)
    if row is None:
        return jsonify({"ok": False, "status": "failed", "error": "live_item_not_found", "message": "خبر پیدا نشد"}), 404
    if str(row.get("panel_status") or "") in _TERMINAL_LIVE_STATUSES:
        return jsonify({"ok": False, "status": "failed", "error": "already_published", "message": "خبر قبلاً منتشر شده"}), 409
    title, body, error = _editor_copy(row)
    if error:
        payload, status = error
        return jsonify(payload), status
    record = _review_record_from_live(row, item_id)
    record["persian_title"] = title
    record["persian_body"] = body
    _write_list(
        "data/editorial_queue.json",
        lambda queue: [record] + [existing for existing in queue if str(existing.get("id") or existing.get("item_id") or "") != item_id],
        "panel: promote live item to review",
    )
    return jsonify({"ok": True, "status": "succeeded", "command_id": "", "review_url": f"/review/{item_id}", "message": "نسخه ویرایش‌شده برای بررسی ذخیره شد"})


@bp.post("/api/newsroom/live/<item_id>/reject")
def reject_live(item_id: str):
    row = _find_live_item(item_id)
    if row is None:
        return jsonify({"ok": False, "status": "failed", "error": "live_item_not_found", "message": "خبر پیدا نشد"}), 404
    if str(row.get("panel_status") or "") in _TERMINAL_LIVE_STATUSES:
        return jsonify({"ok": False, "status": "failed", "error": "already_published", "message": "خبر قبلاً منتشر شده"}), 409
    now = _now_iso()
    record = _review_record_from_live(row, item_id)
    record.update(status="rejected_manual", decision_at=now, updated_at=now)
    _upsert_history(record)
    _remove_from_queue(item_id)
    _remove_live_ids([item_id], mark_seen=True)
    return jsonify({"ok": True, "status": "succeeded", "command_id": "", "message": "خبر رد شد"})


@bp.post("/api/newsroom/live/<item_id>/publish")
def publish_live(item_id: str):
    row = _find_live_item(item_id)
    if row is None:
        return jsonify({"ok": False, "status": "failed", "error": "live_item_not_found", "message": "خبر پیدا نشد"}), 404
    if str(row.get("panel_status") or "") in _TERMINAL_LIVE_STATUSES:
        return jsonify({"ok": False, "status": "failed", "error": "already_published", "message": "خبر قبلاً منتشر شده"}), 409
    title, body, error = _editor_copy(row)
    if error:
        payload, status = error
        return jsonify(payload), status
    source = str(row.get("source") or "").strip()
    source_url = str(row.get("source_url") or row.get("link") or "").strip()
    if not title or not _has_persian(title):
        return jsonify({"ok": False, "status": "failed", "error": "final_not_ready", "message": "تیتر نهایی فارسی آماده نیست"}), 409
    if not source or not source_url:
        return jsonify({"ok": False, "status": "failed", "error": "source_missing", "message": "منبع معتبر خبر موجود نیست"}), 409
    record = _review_record_from_live(row, item_id)
    record["persian_title"] = title
    record["persian_body"] = body
    _write_list(
        "data/editorial_queue.json",
        lambda queue: [record] + [existing for existing in queue if str(existing.get("id") or existing.get("item_id") or "") != item_id],
        "panel: queue live item for V3 publication",
    )
    command_id = _enqueue(
        "v3_publish",
        item_id=item_id,
        news_key=str(row.get("news_key") or item_id),
        source=source,
        source_url=source_url,
        title=title,
        body=body,
        published_at=str(row.get("published_at_source") or row.get("published") or ""),
    )
    return jsonify({"ok": True, "status": "queued", "command_id": command_id, "message": "خبر برای انتشار امن V3 در صف قرار گرفت"}), 202


@bp.get("/api/newsroom/command/<command_id>")
def command_result(command_id: str):
    safe_id = "".join(ch for ch in str(command_id) if ch.isalnum() or ch in "_-")[:96]
    if not safe_id:
        return jsonify({"ok": False, "status": "failed", "error": "invalid_command_id", "message": "شناسه فرمان نامعتبر است"}), 400
    result = _read(f"panel_results/{safe_id}.json", {})
    if not isinstance(result, dict) or not result:
        return jsonify({"ok": True, "status": "queued", "command_id": safe_id, "message": "در صف اجرا"})
    return jsonify(_normalize_result({"ok": result.get("status") not in {"failed"}, **result}, default_status="queued"))
