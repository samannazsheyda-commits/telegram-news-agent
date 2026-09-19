from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, current_app, jsonify, session

from src.formatters import _source_label

from .app import PANEL_STATUS_FA, REASON_FA


bp = Blueprint("ready_feed", __name__)
_TERMINAL_STATUSES = {
    "auto_published",
    "published_auto",
    "published_manual",
    "reconciled_published",
    "rejected_manual",
    "rejected",
    "superseded",
    "blocked",
}
_LIVE_PANEL_MAX_AGE = timedelta(minutes=60)


def _story_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _has_persian(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", str(value or "")))


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


def _is_fresh(row: dict, now: datetime | None = None) -> bool:
    source_time = _source_time(row)
    if source_time is None:
        return True
    resolved_now = now or datetime.now(timezone.utc)
    age = resolved_now.astimezone(timezone.utc) - source_time
    return timedelta(minutes=-5) <= age <= _LIVE_PANEL_MAX_AGE


def _translate_text(value: str, translator) -> tuple[str, str]:
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
        return "", "failed"
    if not _has_persian(translated):
        return "", "failed"
    return translated, "configured"


def _ready_row(row: dict) -> bool:
    return _has_persian(str(row.get("persian_title") or ""))


def _prepare_rows(data, *, limit: int = 100) -> list[dict]:
    """Persist machine Persian copy before a live story is allowed to become visible."""
    translator = current_app.config.get("LIVE_FEED_TRANSLATOR")
    resolved_limit = max(1, min(100, int(limit)))

    for attempt in range(3):
        value, sha = data.read_json("data/panel_live_feed.json", [])
        rows = [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []
        changed = False

        candidates = sorted(
            rows,
            key=lambda row: (_source_time(row) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
            reverse=True,
        )[:resolved_limit]

        for row in candidates:
            if str(row.get("panel_status") or "new") in _TERMINAL_STATUSES:
                continue
            if _ready_row(row):
                if str(row.get("machine_translation_status") or "") != "passed":
                    row["machine_translation_status"] = "passed"
                    row.setdefault("machine_translation_mode", "persisted")
                    changed = True
                continue

            raw_title, raw_body = _raw_fields(row)
            if not raw_title:
                continue

            title_fa, title_mode = _translate_text(raw_title, translator)
            if not title_fa:
                continue

            if raw_body:
                body_fa, body_mode = _translate_text(raw_body, translator)
                if not body_fa:
                    continue
            else:
                body_fa, body_mode = "", title_mode

            mode = "source" if title_mode == body_mode == "source" else "network"
            row.update(
                persian_title=title_fa,
                persian_body=body_fa,
                machine_translation_status="passed",
                machine_translation_mode=mode,
                machine_translation_provider="source" if mode == "source" else "configured",
                machine_translated_at=datetime.now(timezone.utc).isoformat(),
            )
            changed = True

        if changed:
            by_id = {_story_id(row): row for row in candidates if _story_id(row)}
            merged = []
            for row in rows:
                replacement = by_id.get(_story_id(row))
                merged.append(dict(replacement) if replacement is not None else row)
            try:
                data.write_json(
                    "data/panel_live_feed.json",
                    merged,
                    sha,
                    "panel v4.1: translate Persian before dashboard visibility",
                )
                rows = merged
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                if attempt < 2 and status in {409, 422}:
                    continue
                raise

        return rows

    return []


def _active_ready_rows(data, *, limit: int = 40) -> list[dict]:
    now = datetime.now(timezone.utc)
    rows = _prepare_rows(data, limit=max(limit, 40))
    rows = [
        dict(row)
        for row in rows
        if _is_fresh(row, now)
        and str(row.get("panel_status") or "new") not in _TERMINAL_STATUSES
        and _ready_row(row)
    ]
    rows.sort(
        key=lambda row: (_source_time(row) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
        reverse=True,
    )
    return rows[: max(1, min(100, int(limit)))]


def dashboard_live_feed(data) -> list[dict]:
    """Drop-in replacement for panel.app._live_feed used by the production WSGI app."""
    localized: list[dict] = []
    for row in _active_ready_rows(data, limit=100):
        item = dict(row)
        item["display_title"] = str(item.get("persian_title") or "").strip()
        item["source_display"] = _source_label(str(item.get("source") or ""))
        status = str(item.get("panel_status") or "new")
        reason = str(item.get("decision_reason") or "")
        item["panel_status_fa"] = PANEL_STATUS_FA.get(status, "در حال پردازش")
        item["decision_reason_fa"] = REASON_FA.get(reason, "")
        localized.append(item)
    return localized


def _public_row(row: dict) -> dict:
    story_id = _story_id(row)
    raw_title, raw_body = _raw_fields(row)
    title_fa = str(row.get("persian_title") or "").strip()
    body_fa = str(row.get("persian_body") or "").strip()
    status = str(row.get("panel_status") or "new")
    reason = str(row.get("decision_reason") or "")
    source_mode = str(row.get("machine_translation_mode") or "") == "source"
    return {
        "id": story_id,
        "item_id": story_id,
        "title": title_fa,
        "body": body_fa,
        "original_title": raw_title,
        "original_body": raw_body,
        "source": _source_label(str(row.get("source") or "")),
        "source_raw": str(row.get("source") or ""),
        "source_url": str(row.get("source_url") or row.get("link") or ""),
        "panel_status": status,
        "panel_status_fa": PANEL_STATUS_FA.get(status, "در حال پردازش"),
        "decision_reason": reason,
        "decision_reason_fa": REASON_FA.get(reason, ""),
        "published_at_source": str(row.get("published_at_source") or ""),
        "updated_at": str(row.get("updated_at") or row.get("discovered_at") or ""),
        "media_type": str(row.get("media_type") or ""),
        "media_url": str(row.get("video_url") or row.get("media_url") or ""),
        "can_review": bool(story_id),
        "can_publish": bool(story_id and title_fa),
        "can_reject": bool(story_id),
        "translation_mode": "source_persian" if source_mode else "machine_persian",
        "needs_localization": False,
        "machine_translation_status": "passed",
    }


def _terminal_tombstones(data) -> list[dict]:
    value, _ = data.read_json("data/panel_live_feed.json", [])
    rows = [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    tombstones: list[dict] = []
    for row in rows:
        status = str(row.get("panel_status") or "new")
        if status not in _TERMINAL_STATUSES:
            continue
        public = _public_row(row)
        public["panel_status"] = status
        public["can_publish"] = False
        public["can_review"] = False
        public["can_reject"] = False
        tombstones.append(public)
    return tombstones[:40]


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.get("/api/live-feed")
def live_feed():
    data = current_app.extensions["editorial_data"]
    active = [_public_row(row) for row in _active_ready_rows(data, limit=40)]
    items = active + _terminal_tombstones(data)
    response = jsonify(
        {
            "ok": True,
            "items": items,
            "count": len(active),
            "updated_at": active[0]["updated_at"] if active else "",
        }
    )
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response
