from __future__ import annotations

import re
from typing import Any

import requests

from src.managed_sources import system_source_definitions

from .audit_log import append_audit


SETTINGS_PATH = "data/newsroom_settings.json"
V3_STATUS_PATH = "data/newsroom_v3_production_status.json"
STATE_PATH = "state.json"
HISTORY_PATH = "data/editorial_history.json"
CUSTOM_SOURCES_PATH = "data/custom_sources.json"
SOURCE_OVERRIDES_PATH = "data/source_overrides.json"

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


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("@", "").strip().casefold())


def _write_retry(data, path: str, transform, message: str):
    for attempt in range(3):
        current, sha = data.read_json(path, {})
        after = transform(current)
        try:
            data.write_json(path, after, sha, message)
            return current, after
        except requests.HTTPError as exc:
            if attempt < 2 and getattr(exc.response, "status_code", None) in {409, 422}:
                continue
            raise
    raise RuntimeError("assistant_write_conflict")


def _mutate_settings(data, transform, message: str) -> tuple[dict, dict]:
    def apply(current):
        before = dict(current) if isinstance(current, dict) else {}
        return transform(dict(before))

    before, after = _write_retry(data, SETTINGS_PATH, apply, message)
    return (dict(before) if isinstance(before, dict) else {}), dict(after)


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


def _source_action(data, target: str, enabled: bool) -> dict:
    wanted = _normalise_text(target)
    if not wanted:
        return {"intent": "source_toggle", "status": "failed", "requires_confirmation": False, "reply_fa": "اسم منبع مشخص نیست."}

    custom = _read(data, CUSTOM_SOURCES_PATH, [])
    custom = [dict(row) for row in custom if isinstance(row, dict)] if isinstance(custom, list) else []
    system = [dict(row) for row in system_source_definitions()]
    candidates: list[tuple[str, dict]] = [("custom", row) for row in custom] + [("system", row) for row in system]

    def searchable(row: dict) -> str:
        return _normalise_text(" ".join(str(row.get(key) or "") for key in ("name", "identity", "handle", "channel", "query", "feed_url", "website_url")))

    exact = [(kind, row) for kind, row in candidates if wanted in {_normalise_text(str(row.get("name") or "")), _normalise_text(str(row.get("identity") or "")), _normalise_text(str(row.get("handle") or "")), _normalise_text(str(row.get("channel") or ""))}]
    matches = exact or [(kind, row) for kind, row in candidates if wanted and wanted in searchable(row)]
    if not matches:
        return {"intent": "source_toggle", "status": "failed", "requires_confirmation": False, "reply_fa": f"منبع «{target}» را پیدا نکردم."}
    if len(matches) > 1:
        names = "، ".join(str(row.get("name") or row.get("identity") or row.get("id") or "") for _, row in matches[:5])
        return {"intent": "source_toggle", "status": "failed", "requires_confirmation": False, "reply_fa": f"چند منبع مشابه پیدا شد: {names}. اسم دقیق‌تر را بگو."}

    kind, row = matches[0]
    source_id = str(row.get("id") or "").strip()
    display = str(row.get("name") or row.get("identity") or source_id).strip()
    old_active = bool(row.get("active", True))

    if kind == "custom":
        def transform(current):
            rows = [dict(item) for item in current if isinstance(item, dict)] if isinstance(current, list) else []
            for item in rows:
                if str(item.get("id") or "") == source_id:
                    item["active"] = enabled
            return rows
        _write_retry(data, CUSTOM_SOURCES_PATH, transform, "panel v4 luna: toggle custom source")
    else:
        def transform(current):
            overrides = dict(current) if isinstance(current, dict) else {}
            override = dict(overrides.get(source_id) or {})
            override["active"] = enabled
            overrides[source_id] = override
            return overrides
        _write_retry(data, SOURCE_OVERRIDES_PATH, transform, "panel v4 luna: toggle system source")

    append_audit(
        data,
        actor="luna",
        action="enable_source" if enabled else "disable_source",
        target=source_id,
        before={"active": old_active, "name": display},
        after={"active": enabled, "name": display},
        result="ok",
    )
    return {
        "intent": "enable_source" if enabled else "disable_source",
        "status": "succeeded",
        "requires_confirmation": False,
        "source_id": source_id,
        "reply_fa": f"منبع {display} {'روشن' if enabled else 'خاموش'} شد.",
    }


def _priority_action(data, text: str) -> dict:
    target = "ایران" if "ایران" in text else re.split(r"\s+(?:رو|را)\s+اولویت", text, maxsplit=1)[0].strip()
    target = re.sub(r"^(?:اخبار|خبرهای|خبر|مهم)\s+", "", target).strip()
    if not target or len(target) > 80:
        return {"intent": "update_priority_terms", "status": "failed", "requires_confirmation": False, "reply_fa": "موضوع اولویت‌دار مشخص نیست."}

    def transform(settings: dict) -> dict:
        terms = [str(term).strip() for term in settings.get("priority_terms", []) if str(term).strip()] if isinstance(settings.get("priority_terms"), list) else []
        if target.casefold() not in {term.casefold() for term in terms}:
            terms.append(target)
        settings["priority_terms"] = terms[:20]
        return settings

    before, after = _mutate_settings(data, transform, "panel v4 luna: update priority terms")
    append_audit(
        data,
        actor="luna",
        action="update_priority_terms",
        target="settings",
        before={"priority_terms": before.get("priority_terms", [])},
        after={"priority_terms": after.get("priority_terms", [])},
        result="ok",
    )
    return {
        "intent": "update_priority_terms",
        "status": "succeeded",
        "requires_confirmation": False,
        "reply_fa": f"«{target}» به اولویت‌های خبری اضافه شد.",
    }


def handle_control_message(data, message: str) -> dict:
    text = str(message or "").strip()
    if not text:
        return {"intent": "empty", "status": "failed", "requires_confirmation": False, "reply_fa": "پیامت خالی است."}

    lowered = text.casefold()
    nums = _numbers(text)

    source_match = re.search(r"(.+?)(?:\s+(?:رو|را))?\s+(خاموش|روشن)\s+کن(?:ید)?$", text, flags=re.IGNORECASE)
    if source_match:
        return _source_action(data, source_match.group(1).strip(), enabled=source_match.group(2) == "روشن")

    if "اولویت" in lowered and ("بده" in lowered or "اضافه" in lowered):
        return _priority_action(data, text)

    if "سهمیه" in lowered and nums:
        value = nums[-1]
        is_special = "ویژه" in lowered
        max_value = 50 if is_special else 200
        key = "special_quota" if is_special else "daily_quota"
        label = "خبرهای ویژه Luna" if is_special else "خبرهای عادی"
        intent = "update_special_quota" if is_special else "update_daily_quota"
        if not (0 if is_special else 1) <= value <= max_value:
            return {
                "intent": intent,
                "status": "failed",
                "requires_confirmation": False,
                "reply_fa": f"سهمیه {label} معتبر نیست.",
            }

        def transform(settings: dict) -> dict:
            settings[key] = value
            return settings

        before, after = _mutate_settings(data, transform, f"panel v4 luna: update {key}")
        append_audit(
            data,
            actor="luna",
            action=intent,
            target="settings",
            before={key: _safe_int(before.get(key), 5 if is_special else 35)},
            after={key: value},
            result="ok",
        )
        return {
            "intent": intent,
            "status": "succeeded",
            "requires_confirmation": False,
            "value": value,
            "reply_fa": f"سهمیه {label} روی {value} تنظیم شد.",
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
