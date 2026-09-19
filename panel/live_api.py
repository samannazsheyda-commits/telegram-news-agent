from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from flask import Blueprint, current_app, jsonify, request, session

from src.formatters import _source_label
from src.offline_translation import translate_to_fa_offline

from .app import PANEL_STATUS_FA, REASON_FA


bp = Blueprint("live_api", __name__)
_TERMINAL_LIVE_STATUSES = {
    "auto_published",
    "published_auto",
    "published_manual",
    "reconciled_published",
    "rejected_manual",
    "blocked",
    "superseded",
}
_LOCALIZATION_CACHE: dict[str, dict] = {}
_LOCALIZATION_CACHE_LIMIT = 240
_LOCALIZE_BATCH_LIMIT = 12
# Keep a useful live newsroom window instead of silently dropping everything older than one hour.
_LIVE_PANEL_MAX_AGE = timedelta(hours=6)


def _row_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _has_persian(value: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in str(value or ""))


def _raw_fields(row: dict) -> tuple[str, str]:
    title = str(row.get("original_title") or row.get("title") or "").strip()
    body = str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip()
    return title, body


def _parse_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_time(row: dict) -> datetime | None:
    for key in ("published_at_source", "published", "source_timestamp", "discovered_at", "updated_at"):
        parsed = _parse_time(str(row.get(key) or ""))
        if parsed is not None:
            return parsed
    return None


def _is_fresh_for_live_panel(row: dict, now: datetime | None = None) -> bool:
    source_time = _source_time(row)
    if source_time is None:
        return True
    resolved_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = resolved_now - source_time
    return age <= _LIVE_PANEL_MAX_AGE and age >= timedelta(minutes=-5)


def _cache_signature(row: dict) -> str:
    title, body = _raw_fields(row)
    payload = f"{title}\u241f{body}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _cache_get(row: dict) -> dict | None:
    row_id = _row_id(row)
    cached = _LOCALIZATION_CACHE.get(row_id)
    if not isinstance(cached, dict) or cached.get("signature") != _cache_signature(row):
        return None
    return cached


def _cache_put(row: dict, *, title: str, body: str) -> dict:
    row_id = _row_id(row)
    value = {
        "signature": _cache_signature(row),
        "title": title,
        "body": body,
        "translation_mode": "machine_persian",
    }
    _LOCALIZATION_CACHE[row_id] = value
    while len(_LOCALIZATION_CACHE) > _LOCALIZATION_CACHE_LIMIT:
        oldest = next(iter(_LOCALIZATION_CACHE), None)
        if oldest is None:
            break
        _LOCALIZATION_CACHE.pop(oldest, None)
    return value


def _translate_persian(value: str) -> str:
    """Non-authoritative local fallback retained for legacy callers/tests only."""
    text = str(value or "").strip()
    if not text:
        return ""
    if _has_persian(text):
        return text
    try:
        translated = str(translate_to_fa_offline(text) or "").strip()
    except Exception as exc:
        print(f"PANEL_OFFLINE_TRANSLATION_FAILED type={type(exc).__name__}", flush=True)
        return ""
    return translated if _has_persian(translated) else ""


def _machine_translate_persian(value: str, translator) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", "source"
    if _has_persian(text):
        return text, "source"
    if not callable(translator):
        return "", "unavailable"
    try:
        translated = str(translator(text) or "").strip()
    except Exception as exc:
        print(f"PANEL_MACHINE_TRANSLATION_FAILED type={type(exc).__name__}", flush=True)
        return "", "configured_failed"
    if not _has_persian(translated):
        return "", "configured_failed"
    return translated, "configured"


def _persist_machine_translation(
    row_id: str,
    title_fa: str,
    body_fa: str,
    *,
    provider: str,
) -> dict | None:
    data = current_app.extensions["editorial_data"]
    for attempt in range(3):
        value, sha = data.read_json("data/panel_live_feed.json", [])
        rows = [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []
        saved = None
        for row in rows:
            if _row_id(row) != row_id:
                continue
            row["persian_title"] = title_fa
            row["persian_body"] = body_fa
            row["machine_translation_status"] = "passed"
            row["machine_translation_mode"] = "network" if provider == "configured" else provider
            row["machine_translation_provider"] = provider
            row["machine_translated_at"] = datetime.now(timezone.utc).isoformat()
            saved = dict(row)
            break
        if saved is None:
            return None
        try:
            data.write_json(
                "data/panel_live_feed.json",
                rows,
                sha,
                "panel v4.1: persist machine Persian copy",
            )
            return saved
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt < 2 and status in {409, 422}:
                continue
            raise
    return None


def _final_message(row: dict) -> str:
    """Return only a final message that was already persisted by a publish/edit path."""
    return str(row.get("final_message") or row.get("telegram_message") or "").strip()


def _public_row(row: dict, queued_ids: set[str]) -> dict:
    row_id = _row_id(row)
    raw_title, raw_body = _raw_fields(row)
    machine_title = str(row.get("persian_title") or "").strip()
    machine_body = str(row.get("persian_body") or "").strip()
    final_title = str(row.get("final_persian_title") or "").strip()
    final_body = str(row.get("final_persian_body") or "").strip()
    luna_ready = str(row.get("luna_translation_status") or "") == "passed" and _has_persian(final_title)
    cached = _cache_get(row)

    if _has_persian(machine_title):
        title_fa = machine_title
        body_fa = machine_body
        translation_mode = "machine_persian"
        needs_localization = False
    elif _has_persian(raw_title):
        title_fa = raw_title
        body_fa = raw_body
        translation_mode = "source_persian"
        needs_localization = False
    elif luna_ready:
        title_fa = final_title
        body_fa = final_body
        translation_mode = "luna_persian"
        needs_localization = False
    elif cached and _has_persian(str(cached.get("title") or "")):
        title_fa = str(cached.get("title") or "")
        body_fa = str(cached.get("body") or "")
        translation_mode = "cached_preview"
        needs_localization = True
    else:
        title_fa = "عنوان فارسی در حال آماده‌سازی"
        body_fa = ""
        translation_mode = "pending_machine"
        needs_localization = bool(row_id and raw_title)

    status = str(row.get("panel_status") or "new")
    reason = str(row.get("decision_reason") or "")
    has_publishable_persian = _has_persian(machine_title) or _has_persian(raw_title) or luna_ready
    source_time = _source_time(row)
    source_time_iso = source_time.isoformat() if source_time else ""
    return {
        "id": row_id,
        "item_id": row_id,
        "title": title_fa,
        "body": body_fa,
        "original_title": raw_title,
        "original_body": raw_body,
        "source": _source_label(str(row.get("source") or "")),
        "source_raw": str(row.get("source") or ""),
        "source_url": str(row.get("source_url") or ""),
        "panel_status": status,
        "panel_status_fa": PANEL_STATUS_FA.get(status, "در حال پردازش"),
        "decision_reason": reason,
        "decision_reason_fa": REASON_FA.get(reason, ""),
        "published_at_source": str(row.get("published_at_source") or row.get("published") or ""),
        "story_time": source_time_iso,
        "updated_at": str(row.get("updated_at") or row.get("discovered_at") or ""),
        "media_type": str(row.get("media_type") or ""),
        "media_url": str(row.get("video_url") or row.get("media_url") or ""),
        "review_url": f"/review/{row_id}" if row_id in queued_ids else "",
        "can_review": bool(row_id) and status not in _TERMINAL_LIVE_STATUSES,
        "can_publish": bool(row_id) and status not in _TERMINAL_LIVE_STATUSES and has_publishable_persian,
        "can_reject": bool(row_id) and status not in _TERMINAL_LIVE_STATUSES,
        "final_message": _final_message(row),
        "translation_mode": translation_mode,
        "needs_localization": needs_localization,
        "machine_translation_status": str(row.get("machine_translation_status") or ""),
    }


def _raw_rows(limit: int = 100) -> tuple[list[dict], set[str]]:
    data = current_app.extensions["editorial_data"]
    value, _ = data.read_json("data/panel_live_feed.json", [])
    rows = value if isinstance(value, list) else []
    now = datetime.now(timezone.utc)
    fresh_rows = [dict(row) for row in rows if isinstance(row, dict) and _is_fresh_for_live_panel(row, now)]
    fresh_rows.sort(
        key=lambda row: (_source_time(row) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
        reverse=True,
    )
    rows = fresh_rows[: max(1, min(100, int(limit)))]
    queue, _ = data.read_json("data/editorial_queue.json", [])
    queued_ids = {
        str(r.get("id") or r.get("item_id") or "")
        for r in (queue if isinstance(queue, list) else [])
        if isinstance(r, dict)
    }
    return rows, queued_ids


def _fast_rows(limit: int = 100) -> list[dict]:
    rows, queued_ids = _raw_rows(limit)
    return [_public_row(row, queued_ids) for row in rows]


def _feed_revision(items: list[dict]) -> str:
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.get("/api/live-feed")
def live_feed():
    items = _fast_rows(100)
    response = jsonify(
        {
            "ok": True,
            "items": items,
            "count": len(items),
            "revision": _feed_revision(items),
            "updated_at": items[0]["story_time"] if items else "",
        }
    )
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.post("/api/live-feed/localize")
def localize_live_feed():
    payload = request.get_json(silent=True) or {}
    values = payload.get("ids")
    if not isinstance(values, list):
        return jsonify({"ok": False, "error": "invalid_ids"}), 400

    ids: list[str] = []
    seen: set[str] = set()
    for value in values:
        item_id = str(value or "").strip()
        if item_id and item_id not in seen:
            seen.add(item_id)
            ids.append(item_id)
        if len(ids) >= _LOCALIZE_BATCH_LIMIT:
            break
    if not ids:
        return jsonify({"ok": True, "items": []})

    translator = current_app.config.get("LIVE_FEED_TRANSLATOR")
    if not callable(translator):
        return jsonify({"ok": False, "error": "translator_unavailable"}), 503

    data = current_app.extensions["editorial_data"]
    value, _ = data.read_json("data/panel_live_feed.json", [])
    rows = value if isinstance(value, list) else []
    by_id = {_row_id(row): dict(row) for row in rows if isinstance(row, dict) and _row_id(row)}
    queue, _ = data.read_json("data/editorial_queue.json", [])
    queued_ids = {
        str(r.get("id") or r.get("item_id") or "")
        for r in (queue if isinstance(queue, list) else [])
        if isinstance(r, dict)
    }

    localized: list[dict] = []
    for item_id in ids:
        row = by_id.get(item_id)
        if row is None:
            continue
        raw_title, raw_body = _raw_fields(row)
        title_fa, title_mode = _machine_translate_persian(raw_title, translator)
        if not title_fa:
            continue
        if raw_body:
            body_fa, body_mode = _machine_translate_persian(raw_body, translator)
            if not body_fa:
                continue
        else:
            body_fa, body_mode = "", title_mode
        provider = "configured" if "configured" in {title_mode, body_mode} else title_mode
        saved = _persist_machine_translation(
            item_id,
            title_fa,
            body_fa,
            provider=provider,
        )
        if saved is None:
            continue
        _cache_put(saved, title=title_fa, body=body_fa)
        localized_row = _public_row(saved, queued_ids)
        localized_row["translation_mode"] = "machine_persian"
        localized.append(localized_row)

    return jsonify({"ok": True, "items": localized, "translation_mode": "machine_persian"})
