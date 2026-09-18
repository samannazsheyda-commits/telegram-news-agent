from __future__ import annotations

import re
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request, session

from .command_center import _enqueue, _remove_from_queue, _remove_live_ids, _upsert_history, _write_list


bp = Blueprint("panel_v4_actions", __name__)


def _data():
    return current_app.extensions["editorial_data"]


def _rows(path: str) -> list[dict]:
    value, _ = _data().read_json(path, [])
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _row_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _find_item(item_id: str) -> dict | None:
    wanted = str(item_id or "").strip()
    live = next((row for row in _rows("data/panel_live_feed.json") if _row_id(row) == wanted), {})
    queued = next((row for row in _rows("data/editorial_queue.json") if _row_id(row) == wanted), {})
    if not live and not queued:
        return None
    return {**live, **queued}


def _has_persian(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", str(value or "")))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.post("/api/v4/items/<item_id>/publish-final")
def publish_final(item_id: str):
    row = _find_item(item_id)
    if row is None:
        return jsonify({"ok": False, "status": "failed", "error": "item_not_found", "message": "خبر پیدا نشد"}), 404

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "status": "failed", "error": "invalid_payload", "message": "متن نهایی معتبر نیست"}), 400

    title = str(payload.get("title") or row.get("final_persian_title") or row.get("persian_title") or "").strip()
    body = str(payload.get("body") or row.get("final_persian_body") or row.get("persian_body") or "").strip()
    if not title or not _has_persian(title):
        return jsonify({"ok": False, "status": "failed", "error": "missing_final_persian_title", "message": "تیتر نهایی فارسی لازم است"}), 400
    if len(title) > 280 or len(body) > 4000:
        return jsonify({"ok": False, "status": "failed", "error": "final_copy_too_long", "message": "متن نهایی از حد مجاز طولانی‌تر است"}), 400

    source = str(row.get("source") or "").strip()
    source_url = str(row.get("source_url") or row.get("link") or "").strip()
    if not source or not source_url:
        return jsonify({"ok": False, "status": "failed", "error": "source_missing", "message": "منبع یا لینک معتبر خبر موجود نیست"}), 409

    now = _now()
    record = dict(row)
    record.update(
        id=item_id,
        item_id=item_id,
        status="pending",
        luna_status="ready",
        persian_title=title,
        persian_body=body,
        final_persian_title=title,
        final_persian_body=body,
        updated_at=now,
    )
    _write_list(
        "data/editorial_queue.json",
        lambda rows: [record] + [existing for existing in rows if _row_id(existing) != item_id],
        "panel v4: save approved final copy",
    )

    command_id = _enqueue(
        "publish_final",
        item_id=item_id,
        news_key=str(row.get("news_key") or item_id),
        source=source,
        source_url=source_url,
        title=title,
        body=body,
        original_title=str(row.get("original_title") or row.get("title") or ""),
        original_body=str(row.get("original_summary") or row.get("summary") or row.get("body") or ""),
        published_at=str(row.get("published_at_source") or row.get("published") or ""),
    )
    return jsonify({
        "ok": True,
        "status": "queued",
        "command_id": command_id,
        "message": "نسخه تأییدشده برای انتشار در صف قرار گرفت",
    }), 202


@bp.post("/api/v4/items/<item_id>/reject")
def reject_final(item_id: str):
    row = _find_item(item_id)
    if row is None:
        return jsonify({"ok": False, "status": "failed", "error": "item_not_found", "message": "خبر پیدا نشد"}), 404

    now = _now()
    final = dict(row)
    final.update(id=item_id, item_id=item_id, status="rejected_manual", decision_at=now, updated_at=now)
    _upsert_history(final)
    _remove_from_queue(item_id)
    _remove_live_ids([item_id], mark_seen=True)
    return jsonify({"ok": True, "status": "succeeded", "command_id": "", "message": "خبر رد نهایی شد"})
