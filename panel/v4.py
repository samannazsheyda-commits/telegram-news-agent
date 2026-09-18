from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, render_template, request, session

from src.formatters import _source_label

from .command_center import _enqueue, _public_settings, _settings, _write_settings


bp = Blueprint("panel_v4", __name__)
TEHRAN = ZoneInfo("Asia/Tehran")
PAGE_SIZE = 25


def _data():
    return current_app.extensions["editorial_data"]


def _read(path: str, default):
    value, _ = _data().read_json(path, default)
    return value


def _rows(path: str) -> list[dict]:
    value = _read(path, [])
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, dict)]


def _row_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _merged_editorial_rows() -> list[dict]:
    """Merge live-feed discovery data with durable review/Luna state.

    The worker persists Luna previews to editorial_queue.  Merging here keeps
    the original source fields from the live feed while allowing durable queue
    fields (final copy, Luna status, edits) to win.
    """
    merged: dict[str, dict] = {}
    order: list[str] = []
    for row in _rows("data/panel_live_feed.json"):
        item_id = _row_id(row)
        if not item_id:
            continue
        merged[item_id] = dict(row)
        order.append(item_id)
    for row in _rows("data/editorial_queue.json"):
        item_id = _row_id(row)
        if not item_id:
            continue
        if item_id not in merged:
            order.append(item_id)
            merged[item_id] = {}
        merged[item_id] = {**merged[item_id], **row}
    return [merged[item_id] for item_id in order if item_id in merged]


def _find_editorial_item(item_id: str) -> dict | None:
    wanted = str(item_id or "").strip()
    if not wanted:
        return None
    return next((row for row in _merged_editorial_rows() if _row_id(row) == wanted), None)


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_dt(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _today_tehran(value: str) -> bool:
    parsed = _parse_dt(value)
    if parsed is None:
        return False
    return parsed.astimezone(TEHRAN).date() == datetime.now(timezone.utc).astimezone(TEHRAN).date()


def _ago_sort_value(row: dict) -> float:
    for key in ("updated_at", "discovered_at", "published_at_source", "published", "created_at"):
        parsed = _parse_dt(str(row.get(key) or ""))
        if parsed is not None:
            return parsed.timestamp()
    return 0.0


def _paginate(rows: list[dict], page: int, page_size: int = PAGE_SIZE) -> tuple[list[dict], dict]:
    page = max(1, page)
    page_size = max(1, min(50, page_size))
    total = len(rows)
    pages = max(1, ceil(total / page_size))
    page = min(page, pages)
    start = (page - 1) * page_size
    return rows[start : start + page_size], {
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
        "has_prev": page > 1,
        "has_next": start + page_size < total,
    }


def _machine_copy(row: dict) -> tuple[str, str]:
    title = str(
        row.get("machine_translation_title")
        or row.get("machine_title_fa")
        or row.get("translated_title")
        or row.get("offline_title_fa")
        or ""
    ).strip()
    body = str(
        row.get("machine_translation_body")
        or row.get("machine_body_fa")
        or row.get("translated_summary")
        or row.get("offline_body_fa")
        or ""
    ).strip()
    return title, body


def _luna_copy(row: dict) -> tuple[str, str]:
    title = str(row.get("final_persian_title") or row.get("luna_title_fa") or "").strip()
    body = str(row.get("final_persian_body") or row.get("luna_body_fa") or "").strip()
    return title, body


def _public_incoming(row: dict) -> dict:
    machine_title, machine_body = _machine_copy(row)
    luna_title, luna_body = _luna_copy(row)
    item_id = _row_id(row)
    status = str(
        row.get("luna_status")
        or row.get("panel_status")
        or row.get("decision_state")
        or row.get("status")
        or "new"
    ).strip().lower()
    return {
        "id": item_id,
        "source": _source_label(str(row.get("source") or "")),
        "source_raw": str(row.get("source") or ""),
        "source_url": str(row.get("source_url") or row.get("link") or ""),
        "original_title": str(row.get("original_title") or row.get("title") or "").strip(),
        "original_body": str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip(),
        "machine_title": machine_title,
        "machine_body": machine_body,
        "luna_title": luna_title,
        "luna_body": luna_body,
        "luna_reason": str(row.get("luna_reason_fa") or row.get("final_reason_fa") or row.get("decision_reason_fa") or "").strip(),
        "importance": row.get("importance") or row.get("luna_importance"),
        "status": status,
        "decision": str(row.get("luna_decision") or row.get("decision") or "").strip().upper(),
        "dedup": str(row.get("dedup_status") or row.get("duplicate_state") or "").strip(),
        "relevance": row.get("relevance") or row.get("relevance_score"),
        "updated_at": str(row.get("updated_at") or row.get("discovered_at") or row.get("published_at_source") or ""),
        "has_machine": bool(machine_title or machine_body),
        "has_luna": bool(luna_title or luna_body),
        "can_act": bool(item_id) and status not in {"published_auto", "published_manual", "auto_published"},
    }


def _quota_summary(settings: dict, v3: dict) -> dict:
    regular_limit = max(1, _safe_int(settings.get("daily_quota"), 0) or _safe_int(v3.get("daily_limit"), 0) or 35)
    regular_published = max(0, _safe_int(v3.get("daily_published"), 0))
    special_limit = max(0, _safe_int(settings.get("special_quota"), 0) or _safe_int(v3.get("special_limit"), 0) or 5)
    special_used = max(0, _safe_int(v3.get("special_published"), 0))
    return {
        "regular_limit": regular_limit,
        "regular_published": regular_published,
        "regular_remaining": max(0, regular_limit - regular_published),
        "special_limit": special_limit,
        "special_used": special_used,
        "special_remaining": max(0, special_limit - special_used),
    }


def _status_from_age(value: str, *, stale_after: int = 300) -> str:
    parsed = _parse_dt(value)
    if parsed is None:
        return "unknown"
    age = (datetime.now(timezone.utc) - parsed).total_seconds()
    return "ok" if -30 <= age <= stale_after else "warning"


def _health_summary(state: dict, v3: dict, quota: dict) -> dict:
    last_cycle = str(v3.get("last_cycle_at") or state.get("last_cycle_at") or state.get("last_scan_at") or "")
    error = str(v3.get("error") or state.get("last_error") or "").strip()
    error_lower = error.lower()

    agent = "error" if error and not last_cycle else _status_from_age(last_cycle, stale_after=600)
    if _safe_int(v3.get("publish_failed"), 0) > 0:
        telegram = "error"
    elif isinstance(v3.get("telegram_message_id"), int) or _safe_int(v3.get("telegram_writes"), 0) > 0:
        telegram = "ok"
    else:
        telegram = "unknown"

    explicit_luna = str(state.get("luna_state") or v3.get("luna_state") or "").lower()
    if explicit_luna in {"ok", "error", "warning"}:
        luna = explicit_luna
    elif "luna" in error_lower or "provider" in error_lower or "1xai" in error_lower:
        luna = "error"
    else:
        luna = "unknown"

    notes: list[str] = []
    if quota["regular_remaining"] == 0:
        notes.append("سهمیه خبرهای عادی امروز تکمیل شده است.")
    if telegram == "error":
        notes.append("ارسال به تلگرام خطا دارد.")
    if luna == "error":
        notes.append("Luna یا provider فعال خطا دارد.")
    if _safe_int(v3.get("sources_failed"), 0) > 0:
        notes.append(f"{_safe_int(v3.get('sources_failed'), 0)} منبع در آخرین وضعیت خطا داشته‌اند.")
    if str(v3.get("reason") or "") == "no_safe_candidate":
        notes.append("در چرخه اخیر کاندید امن برای انتشار پیدا نشده است.")
    if not notes:
        notes.append("از داده‌های فعلی مانع قطعی برای انتشار دیده نمی‌شود.")

    return {
        "agent": agent,
        "luna": luna,
        "telegram": telegram,
        "last_cycle_at": last_cycle,
        "last_error": error,
        "reason": str(v3.get("reason") or ""),
        "notes": notes,
    }


def _build_snapshot() -> dict:
    settings, _ = _settings()
    state = _read("state.json", {})
    state = state if isinstance(state, dict) else {}
    v3 = _read("data/newsroom_v3_production_status.json", {})
    v3 = v3 if isinstance(v3, dict) else {}
    queue = _rows("data/editorial_queue.json")
    history = _rows("data/editorial_history.json")
    live = _rows("data/panel_live_feed.json")
    sources = _rows("data/custom_sources.json")

    quota = _quota_summary(settings, v3)
    published_today = quota["regular_published"]
    if not published_today:
        published_today = sum(
            1
            for row in history
            if str(row.get("status") or "") in {"published_auto", "published_manual"}
            and _today_tehran(str(row.get("decision_at") or row.get("updated_at") or ""))
        )
        quota["regular_published"] = published_today
        quota["regular_remaining"] = max(0, quota["regular_limit"] - published_today)

    rejected_today = sum(
        1
        for row in history
        if str(row.get("status") or "") in {"rejected_manual", "superseded"}
        and _today_tehran(str(row.get("decision_at") or row.get("updated_at") or ""))
    )
    review_count = sum(1 for row in queue if str(row.get("status") or "pending") == "pending")
    active_sources = sum(1 for row in sources if bool(row.get("active", True)))

    last_publication = str(v3.get("last_published_at") or "")
    if not last_publication:
        published_rows = [row for row in history if str(row.get("status") or "") in {"published_auto", "published_manual"}]
        published_rows.sort(key=_ago_sort_value, reverse=True)
        if published_rows:
            last_publication = str(published_rows[0].get("decision_at") or published_rows[0].get("updated_at") or "")

    return {
        "quota": quota,
        "counts": {
            "incoming": len(live),
            "review": review_count,
            "waiting_luna": _safe_int(v3.get("waiting"), 0),
            "ready": _safe_int(v3.get("ready"), 0),
            "rejected_today": rejected_today,
            "active_sources": active_sources,
        },
        "latest": {
            "last_publication": last_publication,
            "last_cycle_at": str(v3.get("last_cycle_at") or state.get("last_cycle_at") or ""),
        },
        "health": _health_summary(state, v3, quota),
        "settings": {
            **_public_settings(settings),
            "auto_publish": bool(settings.get("auto_publish", True)),
            "manual_approval": bool(settings.get("manual_approval", False)),
            "daily_quota": quota["regular_limit"],
            "special_quota": quota["special_limit"],
            "min_publish_interval": _safe_int(settings.get("min_publish_interval"), 0),
        },
    }


@bp.before_request
def require_admin():
    if not session.get("admin"):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return render_template("login_required.html"), 401
    return None


@bp.get("/incoming")
def incoming():
    rows = _merged_editorial_rows()
    rows.sort(key=_ago_sort_value, reverse=True)
    public = [_public_incoming(row) for row in rows]
    page_rows, pagination = _paginate(public, _safe_int(request.args.get("page"), 1))
    return render_template("incoming.html", items=page_rows, pagination=pagination)


@bp.get("/luna")
def luna():
    rows = _merged_editorial_rows()
    rows.sort(key=_ago_sort_value, reverse=True)
    projected = [_public_incoming(row) for row in rows]
    active = [row for row in projected if row["has_luna"] or row["status"] in {"waiting", "ready", "processing", "failed"}]
    page_rows, pagination = _paginate(active, _safe_int(request.args.get("page"), 1))
    return render_template("luna.html", items=page_rows, pagination=pagination)


@bp.get("/settings")
def settings_page():
    snapshot = _build_snapshot()
    return render_template("settings_v4.html", settings=snapshot["settings"], quota=snapshot["quota"])


@bp.get("/health")
def health_page():
    snapshot = _build_snapshot()
    return render_template("health.html", health=snapshot["health"], counts=snapshot["counts"], quota=snapshot["quota"])


@bp.get("/api/v4/snapshot")
def snapshot_api():
    return jsonify({"ok": True, **_build_snapshot()})


@bp.post("/api/v4/items/<item_id>/luna")
def send_item_to_luna(item_id: str):
    row = _find_editorial_item(item_id)
    if row is None:
        return jsonify({"ok": False, "status": "failed", "error": "item_not_found", "message": "خبر پیدا نشد"}), 404

    final_title, final_body = _luna_copy(row)
    if final_title or final_body:
        return jsonify({
            "ok": True,
            "status": "succeeded",
            "command_id": "",
            "review_url": f"/review/{item_id}",
            "message": "نسخه Luna از قبل آماده است",
        })

    source = str(row.get("source") or "").strip()
    source_url = str(row.get("source_url") or row.get("link") or "").strip()
    original_title = str(row.get("original_title") or row.get("title") or "").strip()
    original_body = str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip()
    if not original_title:
        return jsonify({"ok": False, "status": "failed", "error": "source_text_missing", "message": "متن اصلی خبر موجود نیست"}), 409
    if not source or not source_url:
        return jsonify({"ok": False, "status": "failed", "error": "source_missing", "message": "منبع یا لینک معتبر خبر موجود نیست"}), 409

    command_id = _enqueue(
        "luna_preview",
        item_id=item_id,
        news_key=str(row.get("news_key") or item_id),
        source=source,
        source_url=source_url,
        original_title=original_title,
        original_body=original_body,
        published_at=str(row.get("published_at_source") or row.get("published") or ""),
    )
    return jsonify({
        "ok": True,
        "status": "queued",
        "command_id": command_id,
        "message": "خبر برای نهایی‌سازی با Luna در صف قرار گرفت",
    }), 202


@bp.post("/api/v4/settings/quota")
def update_quota():
    payload = request.get_json(silent=True) or {}
    regular = _safe_int(payload.get("daily_quota"), 0)
    special = _safe_int(payload.get("special_quota"), -1)
    if not 1 <= regular <= 200 or not 0 <= special <= 50:
        return jsonify({"ok": False, "error": "invalid_quota", "message": "سهمیه واردشده معتبر نیست."}), 400

    def transform(settings: dict) -> dict:
        settings["daily_quota"] = regular
        settings["special_quota"] = special
        return settings

    saved = _write_settings(transform)
    return jsonify({"ok": True, "daily_quota": saved.get("daily_quota"), "special_quota": saved.get("special_quota")})
