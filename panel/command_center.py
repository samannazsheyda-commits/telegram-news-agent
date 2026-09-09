from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, session


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
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_CLEAR_SCOPES = {"live", "pending", "published", "rejected"}


def _data():
    return current_app.extensions["editorial_data"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        "poll_seconds": 5,
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
    return jsonify({"ok": True, "available": bool(message or preview), "message": message, **preview})


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
            seen.add(item_id); ids.append(item_id)
    if not ids or len(ids) > 5000:
        return jsonify({"ok": False, "error": "invalid_clear_request"}), 400
    command_id = _enqueue("clear", scope=scope, ids=ids)
    return jsonify({"ok": True, "command_id": command_id, "status": "queued", "count": len(ids)}), 202


@bp.post("/api/command-center/module/<module_name>")
def run_module(module_name: str):
    module = MODULES.get(module_name)
    if module is None:
        return jsonify({"ok": False, "error": "unknown_module"}), 404
    if not module["available"]:
        return jsonify({"ok": False, "error": "module_unavailable", "module": module_name}), 409
    command_id = _enqueue(str(module["action"]))
    return jsonify({"ok": True, "command_id": command_id, "status": "queued"}), 202
