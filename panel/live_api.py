from __future__ import annotations

import re

from flask import Blueprint, current_app, jsonify, session

from src.formatters import SOURCE_FA, _source_label, format_news
from src.sources import NewsItem

from .app import PANEL_STATUS_FA, REASON_FA


bp = Blueprint("live_api", __name__)
_TERMINAL_LIVE_STATUSES = {"auto_published", "published_auto", "published_manual"}
_LATIN_WORD_RE = re.compile(r"\b[A-Za-z]{2,}\b")


def _row_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _has_persian(value: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in str(value or ""))


def _safe_source(source: str) -> str:
    raw = str(source or "").strip()
    if raw in SOURCE_FA or not _LATIN_WORD_RE.search(raw):
        return _source_label(raw)
    if re.search(r"/\s*telegram\s*$", raw, re.I):
        return "منبع خبری / تلگرام"
    if re.search(r"/\s*x\s*$", raw, re.I):
        return "منبع خبری / ایکس"
    return "منبع خبری"


def _final_message(row: dict, title_fa: str, body_fa: str) -> str:
    persisted = str(row.get("final_message") or row.get("telegram_message") or "").strip()
    if persisted:
        return persisted
    if not title_fa or not _has_persian(title_fa):
        return ""
    item = NewsItem(
        key=str(row.get("news_key") or row.get("item_id") or row.get("id") or ""),
        source=_safe_source(str(row.get("source") or "")),
        title=str(row.get("original_title") or row.get("title") or ""),
        summary=str(row.get("original_summary") or row.get("summary") or ""),
        link=str(row.get("source_url") or row.get("link") or ""),
        published=str(row.get("published_at_source") or row.get("published") or ""),
    )
    try:
        return format_news(item, title_fa, body_fa, marker_override=None)
    except Exception:
        return ""


def _fast_rows(limit: int = 40) -> list[dict]:
    data = current_app.extensions["editorial_data"]
    value, _ = data.read_json("data/panel_live_feed.json", [])
    rows = value if isinstance(value, list) else []
    rows = sorted(
        (dict(row) for row in rows if isinstance(row, dict)),
        key=lambda row: str(row.get("updated_at") or row.get("discovered_at") or ""),
        reverse=True,
    )[: max(1, min(100, int(limit)))]
    queue, _ = data.read_json("data/editorial_queue.json", [])
    queued_ids = {
        str(r.get("id") or r.get("item_id") or "")
        for r in (queue if isinstance(queue, list) else [])
        if isinstance(r, dict)
    }
    result: list[dict] = []
    for row in rows:
        row_id = _row_id(row)
        raw_title = str(row.get("original_title") or row.get("title") or "").strip()
        raw_body = str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip()
        title_fa = str(row.get("final_persian_title") or row.get("persian_title") or row.get("display_title") or "").strip()
        if not _has_persian(title_fa):
            title_fa = "عنوان فارسی در حال آماده‌سازی"
        body_fa = str(row.get("final_persian_body") or row.get("persian_body") or "").strip()
        status = str(row.get("panel_status") or "new")
        reason = str(row.get("decision_reason") or "")
        result.append({
            "id": row_id,
            "item_id": row_id,
            "title": title_fa,
            "body": body_fa,
            "original_title": raw_title,
            "original_body": raw_body,
            "source": _safe_source(str(row.get("source") or "")),
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
            "final_message": _final_message(row, title_fa, body_fa),
        })
    return result


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.get("/api/live-feed")
def live_feed():
    items = _fast_rows(40)
    response = jsonify({"ok": True, "items": items, "count": len(items), "updated_at": items[0]["updated_at"] if items else ""})
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response
