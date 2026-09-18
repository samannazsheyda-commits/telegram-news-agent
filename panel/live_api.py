from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request, session

from src.formatters import _source_label

from .app import PANEL_STATUS_FA, REASON_FA


bp = Blueprint("live_api", __name__)
_TERMINAL_LIVE_STATUSES = {"auto_published", "published_auto", "published_manual"}
_MACHINE_CACHE: dict[str, dict] = {}
_MACHINE_CACHE_LIMIT = 240
_MACHINE_BATCH_LIMIT = 12
_LIVE_PANEL_MAX_AGE = timedelta(minutes=60)


def _row_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _has_persian(value: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in str(value or ""))


def _raw_fields(row: dict) -> tuple[str, str]:
    title = str(row.get("original_title") or row.get("title") or "").strip()
    body = str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip()
    return title, body


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_time(row: dict) -> datetime | None:
    for key in ("published_at_source", "published", "source_timestamp", "discovered_at"):
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
    cached = _MACHINE_CACHE.get(row_id)
    if not isinstance(cached, dict) or cached.get("signature") != _cache_signature(row):
        return None
    return cached


def _cache_put(row: dict, *, title: str, body: str) -> dict:
    row_id = _row_id(row)
    value = {
        "signature": _cache_signature(row),
        "title": title,
        "body": body,
        "translation_mode": "machine",
    }
    _MACHINE_CACHE[row_id] = value
    while len(_MACHINE_CACHE) > _MACHINE_CACHE_LIMIT:
        oldest = next(iter(_MACHINE_CACHE), None)
        if oldest is None:
            break
        _MACHINE_CACHE.pop(oldest, None)
    return value


def _translate_machine(value: str) -> str:
    """Return a lightweight operator-only machine translation.

    The production app injects src.services.translate_to_fa, which tries Google
    first and keeps a small network fallback chain. Nothing from this preview is
    persisted or published. Crucially, no Argos model is imported into Gunicorn.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if _has_persian(text):
        return text
    translator = current_app.config.get("LIVE_FEED_TRANSLATOR")
    if not callable(translator):
        return ""
    try:
        translated = str(translator(text) or "").strip()
    except Exception as exc:
        print(f"PANEL_MACHINE_TRANSLATION_FAILED type={type(exc).__name__}", flush=True)
        return ""
    return translated if _has_persian(translated) else ""


def _final_message(row: dict) -> str:
    return str(row.get("final_message") or row.get("telegram_message") or "").strip()


def _public_row(row: dict, queued_ids: set[str]) -> dict:
    row_id = _row_id(row)
    raw_title, raw_body = _raw_fields(row)
    persisted_title = str(row.get("final_persian_title") or row.get("persian_title") or row.get("display_title") or "").strip()
    persisted_body = str(row.get("final_persian_body") or row.get("persian_body") or "").strip()
    cached = _cache_get(row)

    if cached and _has_persian(str(cached.get("title") or "")):
        title_fa = str(cached.get("title") or "")
        body_fa = str(cached.get("body") or "")
        translation_mode = "machine"
        needs_machine_translation = False
    elif _has_persian(raw_title):
        title_fa = raw_title
        body_fa = raw_body
        translation_mode = "source_persian"
        needs_machine_translation = False
    elif _has_persian(persisted_title):
        title_fa = persisted_title
        body_fa = persisted_body
        translation_mode = "persisted_persian"
        needs_machine_translation = False
    else:
        title_fa = ""
        body_fa = ""
        translation_mode = "pending_machine"
        needs_machine_translation = bool(row_id and raw_title)

    status = str(row.get("panel_status") or "new")
    reason = str(row.get("decision_reason") or "")
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
        "published_at_source": str(row.get("published_at_source") or ""),
        "updated_at": str(row.get("updated_at") or row.get("discovered_at") or ""),
        "media_type": str(row.get("media_type") or ""),
        "media_url": str(row.get("video_url") or row.get("media_url") or ""),
        "review_url": f"/review/{row_id}" if row_id in queued_ids else "",
        "can_review": bool(row_id) and status not in _TERMINAL_LIVE_STATUSES,
        "can_publish": bool(row_id) and status not in _TERMINAL_LIVE_STATUSES,
        "can_reject": bool(row_id) and status not in _TERMINAL_LIVE_STATUSES,
        "final_message": _final_message(row),
        "translation_mode": translation_mode,
        "needs_machine_translation": needs_machine_translation,
        # Compatibility alias for older panel code/tests. It now means machine preview.
        "needs_localization": needs_machine_translation,
    }


def _raw_rows(limit: int = 24) -> tuple[list[dict], set[str]]:
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


def _fast_rows(limit: int = 24) -> list[dict]:
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
    items = _fast_rows(24)
    response = jsonify(
        {
            "ok": True,
            "items": items,
            "count": len(items),
            "revision": _feed_revision(items),
            "updated_at": items[0]["updated_at"] if items else "",
        }
    )
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.post("/api/live-feed/machine-translate")
def machine_translate_live_feed():
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
        if len(ids) >= _MACHINE_BATCH_LIMIT:
            break
    if not ids:
        return jsonify({"ok": True, "items": [], "translation_mode": "machine"})

    rows, queued_ids = _raw_rows(100)
    by_id = {_row_id(row): row for row in rows if _row_id(row)}
    translated_rows: list[dict] = []
    for item_id in ids:
        row = by_id.get(item_id)
        if row is None:
            continue
        cached = _cache_get(row)
        if cached is None:
            raw_title, raw_body = _raw_fields(row)
            title_fa = _translate_machine(raw_title)
            if not title_fa:
                continue
            body_fa = _translate_machine(raw_body) if raw_body else ""
            _cache_put(row, title=title_fa, body=body_fa)
        translated_row = _public_row(row, queued_ids)
        translated_row["translation_mode"] = "machine"
        translated_rows.append(translated_row)

    return jsonify({"ok": True, "items": translated_rows, "translation_mode": "machine"})


# Backward-compatible alias while old clients drain from caches.
@bp.post("/api/live-feed/localize")
def localize_live_feed_compat():
    return machine_translate_live_feed()
