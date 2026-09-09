from __future__ import annotations

from flask import Blueprint, current_app, jsonify, session

from .app import PANEL_STATUS_FA, REASON_FA


bp = Blueprint("live_api", __name__)


def _row_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _fast_rows(limit: int = 40) -> list[dict]:
    data = current_app.extensions["editorial_data"]
    value, _ = data.read_json("data/panel_live_feed.json", [])
    rows = value if isinstance(value, list) else []
    rows = sorted(
        (dict(row) for row in rows if isinstance(row, dict)),
        key=lambda row: str(row.get("updated_at") or row.get("discovered_at") or ""),
        reverse=True,
    )[: max(1, min(100, int(limit)))]
    result: list[dict] = []
    for row in rows:
        title = str(row.get("persian_title") or row.get("display_title") or row.get("title") or "بدون عنوان").strip()
        status = str(row.get("panel_status") or "new")
        reason = str(row.get("decision_reason") or "")
        result.append({
            "id": _row_id(row),
            "item_id": _row_id(row),
            "title": title or "بدون عنوان",
            "source": str(row.get("source") or ""),
            "source_url": str(row.get("source_url") or ""),
            "panel_status": status,
            "panel_status_fa": PANEL_STATUS_FA.get(status, "در حال پردازش"),
            "decision_reason": reason,
            "decision_reason_fa": REASON_FA.get(reason, ""),
            "published_at_source": str(row.get("published_at_source") or ""),
            "updated_at": str(row.get("updated_at") or row.get("discovered_at") or ""),
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
    response = jsonify({
        "ok": True,
        "items": items,
        "count": len(items),
        "updated_at": items[0]["updated_at"] if items else "",
    })
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response
