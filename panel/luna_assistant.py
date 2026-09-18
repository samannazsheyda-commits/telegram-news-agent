from __future__ import annotations

import re
from typing import Any

import requests

from .audit_log import append_audit


SETTINGS_PATH = "data/newsroom_settings.json"
V3_STATUS_PATH = "data/newsroom_v3_production_status.json"
STATE_PATH = "state.json"
HISTORY_PATH = "data/editorial_history.json"

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _read(data, path: str, default):
    value, _ = data.read_json(path, default)
    return value


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _numbers(text: str) -> list[int]:
    normalized = str(text or "").translate(_PERSIAN_DIGITS)
    return [int(value) for value in re.findall(r"\d+", normalized)]


def _mutate_settings(data, transform, message: str) -> tuple[dict, dict]:
    for attempt in range(3):
        current, sha = data.read_json(SETTINGS_PATH, {})
        before = dict(current) if isinstance(current, dict) else {}
        after = transform(dict(before))
        try:
            data.write_json(SETTINGS_PATH, after, sha, message)
            return before, after
        except requests.HTTPError as exc:
            if attempt < 2 and getattr(exc.response, "status_code", None) in {409, 422}:
                continue
            raise
    raise RuntimeError("assistant_settings_write_conflict")


def assistant_context(data) -> dict[str, Any]:
    settings = _read(data, SETTINGS_PATH, {})
    settings = settings if isinstance(settings, dict) else {}
    v3 = _read(data, V3_STATUS_PATH, {})
    v3 = v3 if isinstance(v3, dict) else {}
    state = _read(data, STATE_PATH, {})
    state = state if isinstance(state, dict) else {}
    history = _read(data, HISTORY_PATH, [])
    history = [dict(row) for row in history if isinstance(row, dict)] if isinstance(history, list) else []

    regular_limit = max(1, _safe_int(settings.get("daily_quota"), 0) or _safe_int(v3.get("daily_limit"), 0) or 35)
    regular_published = max(0, _safe_int(v3.get("daily_published"), 0))
    special_limit = max(0, _safe_int(settings.get("special_quota"), 0) or _safe_int(v3.get("special_limit"), 0) or 5)
    return {
        "daily_quota": regular_limit,
        "daily_published": regular_published,
        "daily_remaining": max(0, regular_limit - regular_published),
        "special_quota": special_limit,
        "special_used": max(0, _safe_int(v3.get("special_published"), 0)),
        "waiting": max(0, _safe_int(v3.get("waiting"), 0)),
        "ready": max(0, _safe_int(v3.get("ready"), 0)),
        "reason": str(v3.get("reason") or ""),
        "error": str(v3.get("error") or state.get("last_error") or ""),
        "last_cycle_at": str(v3.get("last_cycle_at") or state.get("last_cycle_at") or ""),
        "last_publication_at": str(v3.get("last_published_at") or state.get("last_publication_at") or ""),
        "telegram_state": str(state.get("telegram_state") or "unknown"),
        "sources_ok": _safe_int(v3.get("sources_ok"), _safe_int(state.get("last_sources_ok"), 0)),
        "sources_failed": _safe_int(v3.get("sources_failed"), _safe_int(state.get("last_sources_failed"), 0)),
        "recent_published": [
            {
                "source": str(row.get("source") or ""),
                "title": str(row.get("final_persian_title") or row.get("persian_title") or ""),
                "published_at": str(row.get("decision_at") or row.get("updated_at") or ""),
            }
            for row in history
            if str(row.get("status") or "") in {"published_manual", "published_auto"}
        ][:20],
    }


def _diagnose(data) -> dict:
    context = assistant_context(data)
    pieces = [
        f"امروز {context['daily_published']} خبر عادی از سهمیه {context['daily_quota']} منتشر شده و {context['daily_remaining']} خبر باقی مانده است."
    ]
    if context["waiting"]:
        pieces.append(f"{context['waiting']} مورد در وضعیت انتظار دیده می‌شود و {context['ready']} مورد آماده است.")
    reason = context["reason"]
    if reason == "no_safe_candidate":
        pieces.append("دلیل آخرین چرخه این است که کاندید امن برای انتشار پیدا نشده است.")
    elif reason:
        pieces.append(f"دلیل ثبت‌شده چرخه اخیر: {reason}")
    if context["telegram_state"] == "error":
        pieces.append("وضعیت تلگرام خطا ثبت شده است.")
    if context["error"]:
        pieces.append(f"آخرین خطای ثبت‌شده: {context['error']}")
    if context["sources_failed"]:
        pieces.append(f"{context['sources_failed']} منبع در وضعیت خطا هستند.")
    return {
        "intent": "diagnose_silence",
        "status": "succeeded",
        "requires_confirmation": False,
        "reply_fa": " ".join(pieces),
        "context": context,
    }


def _recent_publications(data, count: int) -> dict:
    context = assistant_context(data)
    rows = context["recent_published"][: max(1, min(20, count))]
    if not rows:
        reply = "در آرشیو فعلی خبر منتشرشده‌ای پیدا نکردم."
    else:
        lines = []
        for index, row in enumerate(rows, start=1):
            title = row["title"] or "بدون عنوان"
            source = row["source"] or "منبع نامشخص"
            lines.append(f"{index}. {title} — {source}")
        reply = "آخرین خبرهای منتشرشده:\n" + "\n".join(lines)
    return {
        "intent": "list_recent_publications",
        "status": "succeeded",
        "requires_confirmation": False,
        "reply_fa": reply,
        "items": rows,
    }


def handle_control_message(data, message: str) -> dict:
    text = str(message or "").strip()
    if not text:
        return {"intent": "empty", "status": "failed", "requires_confirmation": False, "reply_fa": "پیامت خالی است."}

    lowered = text.casefold()
    nums = _numbers(text)

    if "سهمیه" in lowered and nums:
        value = nums[-1]
        if not 1 <= value <= 200:
            return {
                "intent": "update_daily_quota",
                "status": "failed",
                "requires_confirmation": False,
                "reply_fa": "سهمیه خبر عادی باید بین ۱ تا ۲۰۰ باشد.",
            }

        def transform(settings: dict) -> dict:
            settings["daily_quota"] = value
            return settings

        before, after = _mutate_settings(data, transform, "panel v4 luna: update daily quota")
        append_audit(
            data,
            actor="luna",
            action="update_daily_quota",
            target="settings",
            before={"daily_quota": _safe_int(before.get("daily_quota"), 35)},
            after={"daily_quota": value},
            result="ok",
        )
        return {
            "intent": "update_daily_quota",
            "status": "succeeded",
            "requires_confirmation": False,
            "value": value,
            "reply_fa": f"سهمیه خبرهای عادی روی {value} تنظیم شد.",
        }

    if "آخرین" in lowered and ("خبر" in lowered or "منتشر" in lowered):
        count = nums[-1] if nums else 10
        return _recent_publications(data, count)

    if "چرا" in lowered and any(word in lowered for word in ("خبر", "منتشر", "انتشار", "ساکت", "سکوت")):
        return _diagnose(data)

    return {
        "intent": "assistant_chat",
        "status": "needs_luna",
        "requires_confirmation": False,
        "message": text,
        "context": assistant_context(data),
        "reply_fa": "برای این سؤال از Luna سردبیری استفاده می‌کنم.",
    }
