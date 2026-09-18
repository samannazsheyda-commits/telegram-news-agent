from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import requests
from flask import Blueprint, current_app, jsonify, request, session

from src.formatters import _source_label
from src.services import _google_mobile_translate, _google_translate, _polish_fa

from .command_center import _enqueue, _find_live_item, _review_record_from_live, _write_list, _write_settings


bp = Blueprint("panel_v4", __name__)
_MACHINE_CACHE: dict[str, dict] = {}
_MACHINE_CACHE_LIMIT = 300
_TERMINAL = {"auto_published", "published_auto", "published_manual"}


def _data():
    return current_app.extensions["editorial_data"]


def _read(path: str, default):
    value, _ = _data().read_json(path, default)
    return value


def _rows(path: str) -> list[dict]:
    value = _read(path, [])
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _has_persian(value: str) -> bool:
    return any("\u0600" <= char <= "\u06ff" for char in str(value or ""))


def _row_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _source_name(value: str) -> str:
    raw = str(value or "").strip()
    compact = raw.lower().replace("_", "").replace(" ", "")
    if "clashreport" in compact:
        return "Clash Report"
    return _source_label(raw) or raw or "منبع"


def _original_fields(row: dict) -> tuple[str, str]:
    title = str(row.get("original_title") or row.get("title") or "").strip()
    body = str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip()
    return title, body


def _prepared_map() -> dict[str, dict]:
    return {_row_id(row): row for row in _rows("data/panel_luna_prepared.json") if _row_id(row)}


def _public_story(row: dict, prepared: dict[str, dict]) -> dict:
    item_id = _row_id(row)
    original_title, original_body = _original_fields(row)
    staged = prepared.get(item_id) or {}
    status = str(row.get("panel_status") or row.get("status") or "new")
    return {
        "id": item_id,
        "source": _source_name(str(row.get("source") or "")),
        "source_url": str(row.get("source_url") or row.get("link") or ""),
        "original_title": original_title,
        "original_body": original_body,
        "updated_at": str(row.get("updated_at") or row.get("discovered_at") or row.get("fetched_at") or ""),
        "priority": str(row.get("source_priority") or row.get("priority") or "normal"),
        "status": status,
        "prepared": bool(staged),
        "luna_title": str(staged.get("title") or ""),
        "luna_body": str(staged.get("body") or ""),
        "luna_prepared_at": str(staged.get("prepared_at") or ""),
    }


def _revision(stories: list[dict]) -> str:
    payload = [
        (story.get("id"), story.get("updated_at"), story.get("status"), story.get("luna_prepared_at"))
        for story in stories
    ]
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def _settings_public(settings: dict, v3: dict | None = None) -> dict:
    v3 = v3 or {}
    daily_limit = max(1, min(100, _safe_int(settings.get("daily_limit"), _safe_int(v3.get("daily_limit"), 35) or 35)))
    special_limit = max(0, min(20, _safe_int(settings.get("special_limit"), 5)))
    return {
        "daily_limit": daily_limit,
        "special_limit": special_limit,
        "auto_publish": bool(settings.get("auto_publish", True)),
        "emergency_lock": bool(settings.get("emergency_lock", False)),
    }


def _machine_piece(text: str) -> str:
    source = str(text or "").strip()
    if not source:
        return ""
    if _has_persian(source):
        return _polish_fa(source)
    for translator in (_google_translate, _google_mobile_translate):
        try:
            translated = _polish_fa(translator(source, session=requests))
        except Exception as exc:
            print(f"PANEL_GOOGLE_PREVIEW_FAILED backend={translator.__name__} type={type(exc).__name__}", flush=True)
            continue
        if _has_persian(translated):
            return translated
    return ""


def _machine_signature(row: dict) -> str:
    title, body = _original_fields(row)
    return hashlib.sha256(f"{title}\u241f{body}".encode("utf-8")).hexdigest()


def _machine_cache_get(row: dict) -> dict | None:
    item_id = _row_id(row)
    value = _MACHINE_CACHE.get(item_id)
    if not isinstance(value, dict) or value.get("signature") != _machine_signature(row):
        return None
    return value


def _machine_cache_put(row: dict, *, title: str, body: str) -> dict:
    item_id = _row_id(row)
    value = {"signature": _machine_signature(row), "title": title, "body": body}
    _MACHINE_CACHE[item_id] = value
    while len(_MACHINE_CACHE) > _MACHINE_CACHE_LIMIT:
        first = next(iter(_MACHINE_CACHE), None)
        if first is None:
            break
        _MACHINE_CACHE.pop(first, None)
    return value


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.get("/api/v4/snapshot")
def snapshot():
    settings = _read("data/newsroom_settings.json", {})
    settings = settings if isinstance(settings, dict) else {}
    state = _read("state.json", {})
    state = state if isinstance(state, dict) else {}
    v3 = _read("data/newsroom_v3_production_status.json", {})
    v3 = v3 if isinstance(v3, dict) else {}
    prepared = _prepared_map()

    live_rows = _rows("data/panel_live_feed.json")
    live_rows.sort(key=lambda row: str(row.get("updated_at") or row.get("discovered_at") or row.get("fetched_at") or ""), reverse=True)
    live_rows = [row for row in live_rows if str(row.get("panel_status") or "") not in _TERMINAL][:24]
    stories = [_public_story(row, prepared) for row in live_rows]

    public_settings = _settings_public(settings, v3)
    daily_published = max(0, _safe_int(v3.get("daily_published")))
    daily_limit = public_settings["daily_limit"]
    special_published = max(0, _safe_int(v3.get("special_published")))
    payload = {
        "ok": True,
        "engine": str(state.get("newsroom_engine") or "v3"),
        "publishing": public_settings["auto_publish"] and not public_settings["emergency_lock"],
        "last_cycle_at": str(v3.get("last_cycle_at") or state.get("last_cycle_at") or ""),
        "reason": str(v3.get("reason") or ""),
        "error": str(v3.get("error") or ""),
        "counts": {
            "published": daily_published,
            "daily_limit": daily_limit,
            "remaining": max(0, daily_limit - daily_published),
            "ready": max(0, _safe_int(v3.get("ready"))),
            "review": max(0, _safe_int(v3.get("waiting"))),
            "rejected": max(0, _safe_int(v3.get("rejected"))),
            "special_published": special_published,
            "special_limit": public_settings["special_limit"],
        },
        "settings": public_settings,
        "stories": stories,
        "live_revision": _revision(stories),
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }
    return jsonify(payload)


@bp.post("/api/v4/news/<item_id>/machine-translate")
def machine_translate(item_id: str):
    row = _find_live_item(item_id)
    if row is None:
        return jsonify({"ok": False, "error": "live_item_not_found", "message": "خبر پیدا نشد"}), 404
    cached = _machine_cache_get(row)
    if cached:
        return jsonify({"ok": True, "provider": "Google Translate", "title": cached["title"], "body": cached["body"], "cached": True})
    title, body = _original_fields(row)
    translated_title = _machine_piece(title)
    translated_body = _machine_piece(body) if body else ""
    if not translated_title:
        return jsonify({"ok": False, "error": "machine_translation_failed", "message": "ترجمه ماشینی گوگل آماده نشد"}), 502
    _machine_cache_put(row, title=translated_title, body=translated_body)
    return jsonify({"ok": True, "provider": "Google Translate", "title": translated_title, "body": translated_body, "cached": False})


@bp.post("/api/v4/news/<item_id>/prepare-luna")
def prepare_luna(item_id: str):
    row = _find_live_item(item_id)
    if row is None:
        return jsonify({"ok": False, "error": "live_item_not_found", "message": "خبر پیدا نشد"}), 404
    if str(row.get("panel_status") or "") in _TERMINAL:
        return jsonify({"ok": False, "error": "already_published", "message": "خبر قبلاً منتشر شده"}), 409
    title, body = _original_fields(row)
    source = str(row.get("source") or "").strip()
    source_url = str(row.get("source_url") or row.get("link") or "").strip()
    if not title or not source or not source_url:
        return jsonify({"ok": False, "error": "source_missing", "message": "متن یا منبع اصلی خبر کامل نیست"}), 409

    record = _review_record_from_live(row, item_id)
    record["original_title"] = title
    record["original_summary"] = body
    _write_list(
        "data/editorial_queue.json",
        lambda queue: [record] + [existing for existing in queue if _row_id(existing) != item_id],
        "panel v4: queue source for Luna preparation",
    )
    command_id = _enqueue(
        "v3_prepare",
        item_id=item_id,
        news_key=str(row.get("news_key") or item_id),
        source=source,
        source_url=source_url,
        original_title=title,
        original_body=body,
        published_at=str(row.get("published_at_source") or row.get("published") or ""),
    )
    return jsonify({"ok": True, "status": "queued", "command_id": command_id, "message": "خبر برای ترجمه و ویراستاری با لونا در صف قرار گرفت"}), 202


@bp.post("/api/v4/news/<item_id>/publish-prepared")
def publish_prepared(item_id: str):
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    if title and not _has_persian(title):
        return jsonify({"ok": False, "error": "invalid_final_title", "message": "تیتر نهایی فارسی معتبر نیست"}), 400
    command_id = _enqueue("v3_publish_prepared", item_id=item_id, title=title, body=body)
    return jsonify({"ok": True, "status": "queued", "command_id": command_id, "message": "نسخه نهایی برای انتشار در صف قرار گرفت"}), 202


@bp.get("/api/v4/command/<command_id>")
def command_result(command_id: str):
    safe_id = "".join(ch for ch in str(command_id) if ch.isalnum() or ch in "_-")[:96]
    if not safe_id:
        return jsonify({"ok": False, "error": "invalid_command_id"}), 400
    result = _read(f"panel_results/{safe_id}.json", {})
    if not isinstance(result, dict) or not result:
        return jsonify({"ok": True, "status": "queued", "command_id": safe_id, "message": "در صف اجرا"})
    return jsonify({"ok": str(result.get("status") or "") != "failed", **result})


@bp.get("/api/v4/list/<lane>")
def lane_list(lane: str):
    if lane == "review":
        rows = _rows("data/editorial_queue.json")[:100]
    elif lane in {"published", "rejected"}:
        rows = _rows("data/editorial_history.json")
        if lane == "published":
            rows = [row for row in rows if str(row.get("status") or "") in {"published_auto", "published_manual"}]
        else:
            rows = [row for row in rows if str(row.get("status") or "") in {"rejected_manual", "superseded"}]
        rows = rows[:100]
    elif lane == "sources":
        rows = _rows("data/custom_sources.json")[:200]
    else:
        return jsonify({"ok": False, "error": "unknown_lane"}), 404

    public = []
    for row in rows:
        title, body = _original_fields(row)
        public.append({
            "id": _row_id(row),
            "source": _source_name(str(row.get("source") or row.get("name") or "")),
            "title": str(row.get("final_persian_title") or row.get("persian_title") or title or row.get("name") or ""),
            "body": str(row.get("final_persian_body") or row.get("persian_body") or body or ""),
            "status": str(row.get("status") or row.get("panel_status") or ""),
            "updated_at": str(row.get("decision_at") or row.get("updated_at") or row.get("discovered_at") or ""),
            "source_url": str(row.get("source_url") or row.get("url") or ""),
        })
    return jsonify({"ok": True, "lane": lane, "items": public})


@bp.post("/api/v4/settings")
def save_settings():
    payload = request.get_json(silent=True) or {}
    try:
        daily_limit = int(payload.get("daily_limit"))
        special_limit = int(payload.get("special_limit"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_settings", "message": "تعداد خبر معتبر نیست"}), 400
    if not 1 <= daily_limit <= 100 or not 0 <= special_limit <= 20:
        return jsonify({"ok": False, "error": "invalid_settings", "message": "تعداد خبر خارج از محدوده مجاز است"}), 400

    def transform(settings: dict) -> dict:
        settings["daily_limit"] = daily_limit
        settings["special_limit"] = special_limit
        if "auto_publish" in payload:
            settings["auto_publish"] = bool(payload.get("auto_publish"))
            settings["emergency_lock"] = not bool(payload.get("auto_publish"))
        return settings

    saved = _write_settings(transform)
    return jsonify({"ok": True, "settings": _settings_public(saved), "message": "تنظیمات ذخیره شد"})
