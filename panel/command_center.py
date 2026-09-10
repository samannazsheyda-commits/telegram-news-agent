from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, send_file, session


bp = Blueprint("command_center", __name__)

MODULES = {
    "scan": {"available": True, "action": "refresh", "label": "اسکن فوری"},
    "weather": {"available": True, "action": "weather_now", "label": "هواشناسی فردا"},
    "air-traffic": {"available": True, "action": "air_traffic_now", "label": "ترافیک هوایی"},
    "tanker": {"available": True, "action": "tanker_now", "label": "نفتکش‌ها و هرمز"},
    "market": {"available": True, "action": "market_now", "label": "بازار و دلار"},
}
PREVIEW_PATHS = {
    "weather": "data/weather_preview.json",
    "air-traffic": "data/air_traffic_preview.json",
    "tanker": "data/tanker_preview.json",
    "market": "data/market_preview.json",
}
PREVIEW_ACTIONS = {
    "weather": "weather_preview",
    "air-traffic": "air_traffic_preview",
    "tanker": "tanker_preview",
    "market": "market_preview",
}
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_CLEAR_SCOPES = {"live", "pending", "published", "rejected"}
_TERMINAL_LIVE_STATUSES = {"auto_published", "published_auto", "published_manual"}


def _data():
    return current_app.extensions["editorial_data"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _poll_seconds() -> int:
    try:
        return max(1, int(os.environ.get("POLL_SECONDS", "2")))
    except (TypeError, ValueError):
        return 2


def _settings() -> tuple[dict, str | None]:
    value, sha = _data().read_json("data/newsroom_settings.json", {})
    value = value if isinstance(value, dict) else {}
    value.setdefault("auto_publish", True)
    value.setdefault("emergency_lock", False)
    value.setdefault("quiet_mode", False)
    value.setdefault("quiet_start", "00:00")
    value.setdefault("quiet_end", "07:00")
    value.setdefault("freshness_hours", 3)
    return value, sha


def _write_settings(transform) -> dict:
    for _ in range(3):
        value, sha = _settings()
        updated = transform(dict(value))
        updated["updated_at"] = _now_iso()
        try:
            _data().write_json("data/newsroom_settings.json", updated, sha, "command center settings")
            return updated
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status != 409:
                raise
    raise RuntimeError("settings_write_conflict")


def _write_list(path: str, transform, message: str) -> list[dict]:
    for _ in range(3):
        value, sha = _data().read_json(path, [])
        rows = [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []
        updated = transform(rows)
        try:
            _data().write_json(path, updated, sha, message)
            return updated
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status != 409:
                raise
    raise RuntimeError("list_write_conflict")


def _enqueue(action: str, **extra) -> str:
    command_id = uuid4().hex
    payload = {"command_id": command_id, "action": action, "created_at": _now_iso(), **extra}
    _data().write_json(f"panel_commands/{command_id}.json", payload, None, f"command center: {action}")
    return command_id


def _module_public_state() -> dict:
    return {name: {"available": bool(meta["available"]), "label": str(meta["label"])} for name, meta in MODULES.items()}


def _public_settings(settings: dict) -> dict:
    try:
        freshness = max(1, min(48, int(settings.get("freshness_hours") or 3)))
    except (TypeError, ValueError):
        freshness = 3
    return {
        "quiet_mode": bool(settings.get("quiet_mode", False)),
        "quiet_start": str(settings.get("quiet_start") or "00:00"),
        "quiet_end": str(settings.get("quiet_end") or "07:00"),
        "freshness_hours": freshness,
    }


def _age_state(value: str, active_seconds: int = 45) -> str:
    if not value:
        return "unknown"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
        return "active" if age <= active_seconds else "stale"
    except Exception:
        return "unknown"


def _live_row_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _find_live_item(item_id: str) -> dict | None:
    value, _ = _data().read_json("data/panel_live_feed.json", [])
    rows = value if isinstance(value, list) else []
    return next((dict(row) for row in rows if isinstance(row, dict) and _live_row_id(row) == item_id), None)


def _review_record_from_live(row: dict, item_id: str) -> dict:
    now = _now_iso()
    record = dict(row)
    record.update(
        {
            "id": item_id,
            "item_id": item_id,
            "news_key": str(row.get("news_key") or item_id),
            "source": str(row.get("source") or ""),
            "source_url": str(row.get("source_url") or row.get("link") or ""),
            "original_title": str(row.get("original_title") or row.get("title") or ""),
            "original_summary": str(row.get("original_summary") or row.get("summary") or row.get("body") or ""),
            "persian_title": str(row.get("final_persian_title") or row.get("persian_title") or row.get("display_title") or ""),
            "persian_body": str(row.get("final_persian_body") or row.get("persian_body") or ""),
            "published_at_source": str(row.get("published_at_source") or row.get("published") or ""),
            "status": "pending",
            "created_at": str(row.get("created_at") or row.get("discovered_at") or now),
            "updated_at": now,
        }
    )
    return record


def _remove_live_ids(ids: list[str], *, mark_seen: bool = True) -> int:
    targets = set(ids)
    before, _ = _data().read_json("data/panel_live_feed.json", [])
    rows = [dict(row) for row in before if isinstance(row, dict)] if isinstance(before, list) else []
    matched = [row for row in rows if _live_row_id(row) in targets]
    _write_list(
        "data/panel_live_feed.json",
        lambda current: [row for row in current if _live_row_id(row) not in targets],
        "panel: remove live feed items",
    )
    if mark_seen:
        for row in matched:
            key = str(row.get("news_key") or "").strip()
            if key:
                try:
                    _data().mark_news_seen(key)
                except Exception:
                    pass
    return len(matched)


def _remove_from_queue(item_id: str) -> None:
    _write_list(
        "data/editorial_queue.json",
        lambda rows: [row for row in rows if str(row.get("id") or row.get("item_id") or "") != item_id],
        "panel: remove item from editorial queue",
    )


def _upsert_history(record: dict) -> None:
    item_id = str(record.get("id") or record.get("item_id") or "")
    _write_list(
        "data/editorial_history.json",
        lambda rows: [record] + [row for row in rows if str(row.get("id") or row.get("item_id") or "") != item_id],
        "panel: update editorial history",
    )


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.get("/api/command-center/status")
def status():
    settings, _ = _settings()
    live, _ = _data().read_json("data/panel_live_feed.json", [])
    queue, _ = _data().read_json("data/editorial_queue.json", [])
    return jsonify({
        "ok": True,
        "publishing": bool(settings.get("auto_publish", True)) and not bool(settings.get("emergency_lock", False)),
        "emergency_lock": bool(settings.get("emergency_lock", False)),
        "live_count": len(live) if isinstance(live, list) else 0,
        "queue_count": len(queue) if isinstance(queue, list) else 0,
        "poll_seconds": _poll_seconds(),
        "updated_at": settings.get("updated_at", ""),
        "modules": _module_public_state(),
        "settings": _public_settings(settings),
    })


@bp.get("/api/command-center/command/<command_id>")
def command_result(command_id: str):
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", command_id)[:96]
    if not safe_id:
        return jsonify({"ok": False, "error": "invalid_command_id"}), 400
    result, _ = _data().read_json(f"panel_results/{safe_id}.json", {})
    if isinstance(result, dict) and result:
        return jsonify({"ok": True, **result})
    return jsonify({"ok": True, "command_id": safe_id, "status": "queued", "message": "در صف اجرا"})


@bp.get("/api/command-center/health")
def health():
    state, _ = _data().read_json("state.json", {})
    state = state if isinstance(state, dict) else {}
    last_cycle = str(state.get("last_cycle_at") or state.get("last_scan_at") or state.get("updated_at") or "")
    last_publication = str(state.get("last_publication_at") or state.get("last_publish_at") or "")
    last_error = str(state.get("last_error") or "")
    telegram_state = str(state.get("telegram_state") or "unknown")
    if telegram_state not in {"ok", "error", "unknown"}:
        telegram_state = "unknown"
    return jsonify({
        "ok": True,
        "agent_state": _age_state(last_cycle),
        "last_cycle_at": last_cycle,
        "last_publication_at": last_publication,
        "last_error": last_error,
        "telegram_state": telegram_state,
        "sources_ok": int(state.get("last_sources_ok") or 0),
        "sources_failed": int(state.get("last_sources_failed") or 0),
        "items_fetched": int(state.get("last_items_fetched") or 0),
        "panel_commands": int(state.get("last_panel_commands") or 0),
        "cycle_rc": int(state.get("last_cycle_rc") or 0),
    })


@bp.get("/api/command-center/module/<module_name>/preview")
def module_preview(module_name: str):
    path = PREVIEW_PATHS.get(module_name)
    if not path:
        return jsonify({"ok": False, "error": "unknown_module"}), 404
    preview, _ = _data().read_json(path, {})
    if not isinstance(preview, dict) or not preview:
        return jsonify({"ok": True, "available": False, "message": "", "generated_at": ""})
    message = str(preview.get("message") or preview.get("text") or preview.get("caption") or "")
    public = dict(preview)
    if module_name == "air-traffic" and preview.get("image_path"):
        public["image_url"] = "/api/command-center/module/air-traffic/preview/image"
    return jsonify({"ok": True, "available": bool(message or preview), "message": message, **public})


@bp.get("/api/command-center/module/air-traffic/preview/image")
def air_traffic_preview_image():
    backend = _data()
    root_value = getattr(backend, "root", None)
    if root_value is None:
        return jsonify({"ok": False, "error": "preview_image_unavailable"}), 404
    preview, _ = backend.read_json("data/air_traffic_preview.json", {})
    image_rel = str(preview.get("image_path") or "data/air_traffic_preview.png") if isinstance(preview, dict) else "data/air_traffic_preview.png"
    root = Path(root_value).resolve()
    candidate = Path(image_rel)
    image = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if root != image and root not in image.parents:
        return jsonify({"ok": False, "error": "invalid_preview_image"}), 400
    if not image.is_file():
        return jsonify({"ok": False, "error": "preview_image_unavailable"}), 404
    response = send_file(image, mimetype="image/png", max_age=0)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.post("/api/command-center/module/<module_name>/preview")
def build_module_preview(module_name: str):
    action = PREVIEW_ACTIONS.get(module_name)
    if not action:
        return jsonify({"ok": False, "error": "unknown_module"}), 404
    module = MODULES.get(module_name)
    if module is None or not module.get("available"):
        return jsonify({"ok": False, "error": "module_unavailable", "module": module_name}), 409
    command_id = _enqueue(action)
    return jsonify({"ok": True, "command_id": command_id, "status": "queued"}), 202


@bp.post("/api/command-center/publishing")
def publishing():
    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get("enabled"))

    def transform(settings: dict) -> dict:
        settings["auto_publish"] = enabled
        settings["emergency_lock"] = not enabled
        return settings

    settings = _write_settings(transform)
    return jsonify({"ok": True, "publishing": bool(settings.get("auto_publish")) and not bool(settings.get("emergency_lock"))})


@bp.post("/api/command-center/settings")
def update_settings():
    payload = request.get_json(silent=True) or {}
    try:
        freshness = int(payload.get("freshness_hours"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_settings"}), 400
    quiet_start = str(payload.get("quiet_start") or "").strip()
    quiet_end = str(payload.get("quiet_end") or "").strip()
    if not 1 <= freshness <= 48 or not _TIME_RE.fullmatch(quiet_start) or not _TIME_RE.fullmatch(quiet_end):
        return jsonify({"ok": False, "error": "invalid_settings"}), 400
    quiet_mode = bool(payload.get("quiet_mode"))

    def transform(settings: dict) -> dict:
        settings["freshness_hours"] = freshness
        settings["quiet_mode"] = quiet_mode
        settings["quiet_start"] = quiet_start
        settings["quiet_end"] = quiet_end
        return settings

    settings = _write_settings(transform)
    return jsonify({"ok": True, "settings": _public_settings(settings)})


@bp.post("/api/command-center/clear")
def clear_items():
    payload = request.get_json(silent=True) or {}
    scope = str(payload.get("scope") or "").strip()
    ids_value = payload.get("ids")
    if scope not in _CLEAR_SCOPES or not isinstance(ids_value, list):
        return jsonify({"ok": False, "error": "invalid_clear_request"}), 400
    ids, seen = [], set()
    for value in ids_value:
        item_id = str(value or "").strip()
        if item_id and item_id not in seen:
            seen.add(item_id)
            ids.append(item_id)
    if not ids or len(ids) > 5000:
        return jsonify({"ok": False, "error": "invalid_clear_request"}), 400
    if scope == "live":
        count = _remove_live_ids(ids, mark_seen=True)
        return jsonify({"ok": True, "status": "succeeded", "count": count, "message": f"{count} خبر از ورودی زنده حذف شد"})
    command_id = _enqueue("clear", scope=scope, ids=ids)
    return jsonify({"ok": True, "command_id": command_id, "status": "queued", "count": len(ids)}), 202


@bp.post("/api/command-center/live/<item_id>/review")
def promote_live_to_review(item_id: str):
    row = _find_live_item(item_id)
    if row is None:
        return jsonify({"ok": False, "error": "live_item_not_found"}), 404
    if str(row.get("panel_status") or "") in _TERMINAL_LIVE_STATUSES:
        return jsonify({"ok": False, "error": "already_published"}), 409
    record = _review_record_from_live(row, item_id)

    def transform(queue: list[dict]) -> list[dict]:
        return [record] + [existing for existing in queue if str(existing.get("id") or existing.get("item_id") or "") != item_id]

    _write_list("data/editorial_queue.json", transform, "panel: promote live item to review")
    return jsonify({"ok": True, "review_url": f"/review/{item_id}"})


@bp.post("/api/command-center/live/<item_id>/reject")
def reject_live_item(item_id: str):
    row = _find_live_item(item_id)
    if row is None:
        return jsonify({"ok": False, "error": "live_item_not_found"}), 404
    if str(row.get("panel_status") or "") in _TERMINAL_LIVE_STATUSES:
        return jsonify({"ok": False, "error": "already_published"}), 409
    now = _now_iso()
    record = _review_record_from_live(row, item_id)
    record.update(status="rejected_manual", decision_at=now, updated_at=now)
    _upsert_history(record)
    _remove_from_queue(item_id)
    _remove_live_ids([item_id], mark_seen=True)
    return jsonify({"ok": True, "status": "rejected", "message": "خبر رد و از ورودی زنده حذف شد"})


@bp.post("/api/command-center/live/<item_id>/publish")
def publish_live_item(item_id: str):
    row = _find_live_item(item_id)
    if row is None:
        return jsonify({"ok": False, "error": "live_item_not_found"}), 404
    if str(row.get("panel_status") or "") in _TERMINAL_LIVE_STATUSES:
        return jsonify({"ok": False, "error": "already_published"}), 409
    title = str(row.get("final_persian_title") or row.get("persian_title") or "").strip()
    body = str(row.get("final_persian_body") or row.get("persian_body") or "").strip()
    if not title or not any("\u0600" <= ch <= "\u06ff" for ch in title):
        return jsonify({"ok": False, "error": "final_not_ready"}), 409
    record = _review_record_from_live(row, item_id)
    record["persian_title"] = title
    record["persian_body"] = body

    def transform(queue: list[dict]) -> list[dict]:
        return [record] + [existing for existing in queue if str(existing.get("id") or existing.get("item_id") or "") != item_id]

    _write_list("data/editorial_queue.json", transform, "panel: queue live item for publication")
    command_id = _enqueue("publish", item_id=item_id, title=title, body=body)
    return jsonify({"ok": True, "command_id": command_id, "status": "queued", "message": "خبر برای انتشار ارسال شد"}), 202


@bp.post("/api/command-center/module/<module_name>")
def run_module(module_name: str):
    module = MODULES.get(module_name)
    if module is None:
        return jsonify({"ok": False, "error": "unknown_module"}), 404
    if not module["available"]:
        return jsonify({"ok": False, "error": "module_unavailable", "module": module_name}), 409
    command_id = _enqueue(str(module["action"]))
    return jsonify({"ok": True, "command_id": command_id, "status": "queued"}), 202
