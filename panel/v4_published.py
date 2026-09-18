from __future__ import annotations

from math import ceil

from flask import Blueprint, current_app, render_template, request, session

from src.formatters import _source_label


bp = Blueprint("panel_v4_published", __name__)
PAGE_SIZE = 25
PUBLISHED_STATUSES = {"published_manual", "published_auto"}


def _data():
    return current_app.extensions["editorial_data"]


def _rows(path: str) -> list[dict]:
    value, _ = _data().read_json(path, [])
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _safe_int(value, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _public_row(row: dict) -> dict:
    title = str(row.get("final_persian_title") or row.get("persian_title") or row.get("original_title") or "").strip()
    body = str(row.get("final_persian_body") or row.get("persian_body") or "").strip()
    return {
        "id": str(row.get("id") or row.get("item_id") or "").strip(),
        "source": _source_label(str(row.get("source") or "")),
        "source_raw": str(row.get("source") or ""),
        "source_url": str(row.get("source_url") or ""),
        "status": str(row.get("status") or ""),
        "title": title,
        "body": body,
        "published_at": str(row.get("decision_at") or row.get("updated_at") or ""),
        "telegram_message_id": row.get("telegram_message_id"),
        "v3_story_id": str(row.get("v3_story_id") or ""),
    }


def _matches(row: dict, query: str, source: str, status: str) -> bool:
    if status and row["status"] != status:
        return False
    if source and row["source_raw"].casefold() != source.casefold():
        return False
    if query:
        haystack = " ".join((row["title"], row["body"], row["source"], row["source_raw"])).casefold()
        if query.casefold() not in haystack:
            return False
    return True


@bp.before_request
def require_admin():
    if not session.get("admin"):
        from flask import redirect, url_for
        return redirect(url_for("login", next=request.path))
    return None


@bp.get("/published")
def published():
    query = str(request.args.get("q") or "").strip()
    source = str(request.args.get("source") or "").strip()
    status = str(request.args.get("status") or "").strip()
    if status and status not in PUBLISHED_STATUSES:
        status = ""

    all_rows = [_public_row(row) for row in _rows("data/editorial_history.json") if str(row.get("status") or "") in PUBLISHED_STATUSES]
    all_rows.sort(key=lambda row: row["published_at"], reverse=True)
    sources = sorted({row["source_raw"] for row in all_rows if row["source_raw"]}, key=str.casefold)
    filtered = [row for row in all_rows if _matches(row, query, source, status)]

    page = max(1, _safe_int(request.args.get("page"), 1))
    pages = max(1, ceil(len(filtered) / PAGE_SIZE))
    page = min(page, pages)
    start = (page - 1) * PAGE_SIZE
    items = filtered[start:start + PAGE_SIZE]
    pagination = {
        "page": page,
        "pages": pages,
        "page_size": PAGE_SIZE,
        "total": len(filtered),
        "has_prev": page > 1,
        "has_next": start + PAGE_SIZE < len(filtered),
    }
    return render_template(
        "published_v4.html",
        items=items,
        pagination=pagination,
        filters={"q": query, "source": source, "status": status},
        sources=sources,
    )
