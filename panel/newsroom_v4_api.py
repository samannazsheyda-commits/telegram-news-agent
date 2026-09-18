from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request, session

from .command_center import _enqueue, _find_live_item, _review_record_from_live, _settings, _write_list, _write_settings


bp = Blueprint("newsroom_v4_api", __name__)
_TERMINAL = {"succeeded", "failed", "reconciled", "ambiguous"}


def _data():
    return current_app.extensions["editorial_data"]


def _read(path: str, default):
    value, _ = _data().read_json(path, default)
    return value


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_id(row: dict) -> str:
    return str(row.get("id") or row.get("item_id") or row.get("news_key") or "").strip()


def _source_fields(row: dict, item_id: str) -> dict[str, str]:
    return {
        "item_id": item_id,
        "news_key": str(row.get("news_key") or item_id),
        "source": str(row.get("source") or "").strip(),
        "source_url": str(row.get("source_url") or row.get("link") or "").strip(),
        "original_title": str(row.get("original_title") or row.get("title") or "").strip(),
        "original_body": str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip(),
        "published_at": str(row.get("published_at_source") or row.get("published") or "").strip(),
    }


def _queue_record(row: dict, item_id: str) -> None:
    record = _review_record_from_live(row, item_id)
    record["original_title"] = str(row.get("original_title") or row.get("title") or "").strip()
    record["original_summary"] = str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip()
    _write_list(
        "data/editorial_queue.json",
        lambda queue: [record] + [existing for existing in queue if _row_id(existing) != item_id],
        "panel v4: queue immutable source",
    )


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.get("/api/newsroom/v4/status")
def status():
    settings, _ = _settings()
    v3 = _read("data/newsroom_v3_production_status.json", {})
    v3 = v3 if isinstance(v3, dict) else {}
    daily_limit = max(1, min(100, _safe_int(settings.get("daily_limit"), _safe_int(v3.get("daily_limit"), 35))))
    special_limit = max(0, min(10, _safe_int(settings.get("special_limit"), 5)))
    daily_published = max(0, _safe_int(v3.get("daily_published"), 0))
    return jsonify(
        {
            "ok": True,
            "engine": "v3",
            "publishing": bool(settings.get("auto_publish", True)) and not bool(settings.get("emergency_lock", False)),
            "daily_limit": daily_limit,
            "daily_published": daily_published,
            "daily_remaining": max(0, daily_limit - daily_published),
            "special_limit": special_limit,
            "special_published": max(0, _safe_int(v3.get("special_published"), 0)),
            "ready": max(0, _safe_int(v3.get("ready"), 0)),
            "waiting": max(0, _safe_int(v3.get("waiting"), 0)),
            "rejected": max(0, _safe_int(v3.get("rejected"), 0)),
            "duplicates": max(0, _safe_int(v3.get("duplicates"), 0)),
            "items_fetched": max(0, _safe_int(v3.get("items_fetched"), 0)),
            "sources_ok": max(0, _safe_int(v3.get("sources_ok"), 0)),
            "sources_failed": max(0, _safe_int(v3.get("sources_failed"), 0)),
            "reason": str(v3.get("reason") or ""),
            "error": str(v3.get("error") or ""),
            "last_cycle_at": str(v3.get("last_cycle_at") or ""),
            "updated_at": _now_iso(),
        }
    )


@bp.post("/api/newsroom/v4/daily-limit")
def daily_limit():
    payload = request.get_json(silent=True) or {}
    limit = max(1, min(100, _safe_int(payload.get("daily_limit"), 35)))
    special = max(0, min(10, _safe_int(payload.get("special_limit"), 5)))

    def transform(value: dict) -> dict:
        value["daily_limit"] = limit
        value["special_limit"] = special
        return value

    saved = _write_settings(transform)
    return jsonify(
        {
            "ok": True,
            "status": "succeeded",
            "daily_limit": int(saved.get("daily_limit") or limit),
            "special_limit": int(saved.get("special_limit") or special),
            "message": "سهمیه روزانه ذخیره شد",
        }
    )


@bp.post("/api/newsroom/live/<item_id>/luna")
def luna_preview(item_id: str):
    row = _find_live_item(item_id)
    if row is None:
        return jsonify({"ok": False, "error": "live_item_not_found", "message": "خبر پیدا نشد"}), 404
    fields = _source_fields(row, item_id)
    if not fields["original_title"] or not fields["source"] or not fields["source_url"]:
        return jsonify({"ok": False, "error": "source_missing", "message": "متن یا منبع اصلی خبر کامل نیست"}), 409
    _queue_record(row, item_id)
    command_id = _enqueue("v3_prepare", **fields)
    return jsonify({"ok": True, "status": "queued", "command_id": command_id, "message": "خبر برای ترجمه و ویراستاری لونا فرستاده شد؛ هنوز منتشر نشده"}), 202


@bp.post("/api/newsroom/live/<item_id>/publish-prepared")
def publish_prepared(item_id: str):
    row = _find_live_item(item_id)
    if row is None:
        return jsonify({"ok": False, "error": "live_item_not_found", "message": "خبر پیدا نشد"}), 404
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "luna_preview_required", "message": "اول نسخه لونا را آماده کن"}), 409
    fields = _source_fields(row, item_id)
    _queue_record(row, item_id)
    command_id = _enqueue("v3_publish_prepared", **fields, title=title, body=body)
    return jsonify({"ok": True, "status": "queued", "command_id": command_id, "message": "نسخه دیده‌شده لونا برای انتشار فرستاده شد"}), 202


@bp.get("/api/newsroom/v4/command/<command_id>")
def command_result(command_id: str):
    safe_id = "".join(ch for ch in str(command_id) if ch.isalnum() or ch in "_-")[:96]
    if not safe_id:
        return jsonify({"ok": False, "status": "failed", "error": "invalid_command_id"}), 400
    result = _read(f"panel_results/{safe_id}.json", {})
    if not isinstance(result, dict) or not result:
        return jsonify({"ok": True, "status": "queued", "command_id": safe_id, "message": "در صف اجرا"})
    status = str(result.get("status") or "queued")
    return jsonify(
        {
            "ok": status != "failed",
            "status": status,
            "command_id": safe_id,
            "message": str(result.get("message") or ""),
            "error": str(result.get("error") or ""),
            "title": str(result.get("title") or ""),
            "body": str(result.get("body") or ""),
            "story_id": str(result.get("story_id") or ""),
            "telegram_message_id": result.get("telegram_message_id") if isinstance(result.get("telegram_message_id"), int) else None,
            "terminal": status in _TERMINAL,
        }
    )
