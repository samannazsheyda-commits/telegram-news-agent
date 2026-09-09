from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from flask import Blueprint, current_app, jsonify, session

from src.persian_datetime import tehran_persian_date_time

from .app import PANEL_STATUS_FA, REASON_FA


bp = Blueprint("live_api", __name__)

_ARTICLE_PATTERNS = (
    r"^\s*(?:analysis|opinion|explainer|commentary|factbox|viewpoint|guide|timeline|live\s+blog)\b",
    r"\b(?:what\s+we\s+know|what\s+to\s+know|everything\s+you\s+need\s+to\s+know|why\s+it\s+matters)\b",
    r"^\s*(?:تحلیل|یادداشت|نظر|راهنما|پرسش\s+و\s+پاسخ|آنچه\s+می[‌ ]?دانیم)\b",
)
_TEASER_PATTERNS = (
    r"^\s*(?:watch|more|developing|read\s+more|live)\s*[:\-]",
    r"^\s*(?:ببینید|بیشتر|در\s+حال\s+تکمیل)\s*[:：\-]",
)
_EVENT_TERMS = (
    "حمله", "موشک", "پهپاد", "انفجار", "رهگیری", "شلیک", "اصابت", "کشته", "بازداشت", "توقیف",
    "attack", "strike", "missile", "drone", "explosion", "intercept", "launched", "hit", "seized",
)
_LATIN_REPLACEMENTS = (
    (re.compile(r"\bCENTCOM\b", re.I), "سنتکام"),
    (re.compile(r"\bIRGC\b", re.I), "سپاه پاسداران"),
    (re.compile(r"\bIDF\b", re.I), "ارتش اسرائیل"),
    (re.compile(r"\bU\.?S\.?\b", re.I), "آمریکا"),
    (re.compile(r"\bUSA\b", re.I), "آمریکا"),
)


def _row_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _has_persian(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", str(value or "")))


def _clean_persian_title(value: str) -> str:
    text = re.sub(r"https?://\S+", "", str(value or "")).strip()
    for pattern, replacement in _LATIN_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    # English source glosses and raw untranslated words belong only in the
    # expandable original-text block, never in the default RTL headline.
    text = re.sub(r"\((?=[^)]*[A-Za-z])[^)]*\)", "", text)
    if _has_persian(text):
        text = re.sub(r"(?<![\w])(?:[A-Za-z][A-Za-z.'’_-]*)(?:\s+[A-Za-z][A-Za-z.'’_-]*)*(?![\w])", " ", text)
    text = re.sub(r"\s+([،؛:,.!?؟])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip(" -–—:،")


def _primary_news_candidate(title: str, persian_title: str = "") -> bool:
    combined = " ".join(part for part in (str(title or "").strip(), str(persian_title or "").strip()) if part)
    clean = re.sub(r"\s+", " ", combined).strip()
    lower = clean.lower()
    if not clean:
        return False
    if "?" in clean or "؟" in clean:
        return False
    if any(re.search(pattern, lower, re.I) for pattern in _ARTICLE_PATTERNS):
        return False
    if any(re.search(pattern, lower, re.I) for pattern in _TEASER_PATTERNS):
        return False
    # A tiny fragment without an event/action is not useful as a newsroom row.
    words = re.findall(r"[\w\u0600-\u06ff]+", clean, flags=re.UNICODE)
    if len(words) < 4 and not any(term in lower for term in _EVENT_TERMS):
        return False
    return True


def _parse_time(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(raw)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fa_time(value: str) -> str:
    dt = _parse_time(value)
    if dt is None:
        return ""
    date_text, time_text = tehran_persian_date_time(dt)
    return f"{date_text} — {time_text}"


def _fast_rows(limit: int = 40) -> list[dict]:
    data = current_app.extensions["editorial_data"]
    value, _ = data.read_json("data/panel_live_feed.json", [])
    rows = value if isinstance(value, list) else []
    rows = sorted(
        (dict(row) for row in rows if isinstance(row, dict)),
        key=lambda row: str(row.get("updated_at") or row.get("discovered_at") or ""),
        reverse=True,
    )
    result: list[dict] = []
    now = datetime.now(timezone.utc)
    for row in rows:
        original_title = str(row.get("original_title") or row.get("title") or "").strip()
        prepared_fa = str(row.get("persian_title") or row.get("display_title") or "").strip()
        if not _primary_news_candidate(original_title, prepared_fa):
            continue
        title_fa = _clean_persian_title(prepared_fa) if _has_persian(prepared_fa) else "عنوان فارسی در حال آماده‌سازی"
        if not title_fa:
            title_fa = "عنوان فارسی در حال آماده‌سازی"
        status = str(row.get("panel_status") or "new")
        reason = str(row.get("decision_reason") or "")
        source_time = str(row.get("published_at_source") or row.get("source_time") or "")
        arrival_time = str(row.get("discovered_at") or row.get("fetched_at") or row.get("updated_at") or "")
        arrival_dt = _parse_time(arrival_time)
        age_seconds = max(0, int((now - arrival_dt).total_seconds())) if arrival_dt is not None else 0
        item_id = _row_id(row)
        result.append({
            "id": item_id,
            "item_id": item_id,
            "title": title_fa,
            "title_fa": title_fa,
            "original_title": original_title,
            "has_original": bool(original_title and original_title != title_fa),
            "source": str(row.get("source") or ""),
            "source_url": str(row.get("source_url") or ""),
            "panel_status": status,
            "panel_status_fa": PANEL_STATUS_FA.get(status, "در حال پردازش"),
            "decision_reason": reason,
            "decision_reason_fa": REASON_FA.get(reason, ""),
            "source_time_iso": source_time,
            "source_time_fa": _fa_time(source_time),
            "arrival_time_iso": arrival_time,
            "arrival_time_fa": _fa_time(arrival_time),
            "age_seconds": age_seconds,
            # Backward-compatible keys for older panel JS during deployment.
            "published_at_source": source_time,
            "updated_at": str(row.get("updated_at") or arrival_time),
        })
        if len(result) >= max(1, min(100, int(limit))):
            break
    return result


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.get("/api/live-feed")
def live_feed():
    items = _fast_rows(80)
    response = jsonify({
        "ok": True,
        "items": items,
        "count": len(items),
        "updated_at": items[0]["updated_at"] if items else "",
    })
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response
