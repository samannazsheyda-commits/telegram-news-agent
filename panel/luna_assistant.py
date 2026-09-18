from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, session

from .command_center import _settings, _write_list, _write_settings


bp = Blueprint("luna_assistant", __name__)
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _data():
    return current_app.extensions["editorial_data"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: str, default):
    value, _ = _data().read_json(path, default)
    return value


def _rows(path: str) -> list[dict]:
    value = _read(path, [])
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _audit(action: str, target: str, *, actor: str = "luna", before=None, after=None, result: str = "ok") -> None:
    record = {
        "timestamp": _now_iso(),
        "actor": actor,
        "action": action,
        "target": target,
        "before": before,
        "after": after,
        "result": result,
    }
    _write_list("data/panel_audit_log.json", lambda rows: ([record] + rows)[:500], "panel v4: assistant audit")


def _save_pending(action: str, payload: dict, summary_fa: str) -> str:
    action_id = uuid4().hex
    record = {
        "id": action_id,
        "action": action,
        "payload": payload,
        "summary_fa": summary_fa,
        "created_at": _now_iso(),
        "status": "pending",
    }
    _write_list("data/panel_pending_actions.json", lambda rows: ([record] + rows)[:100], "panel v4: pending assistant action")
    return action_id


def _published_rows(limit: int = 20) -> list[dict]:
    rows = [row for row in _rows("data/editorial_history.json") if str(row.get("status") or "") in {"published_auto", "published_manual"}]
    rows.sort(key=lambda row: str(row.get("decision_at") or row.get("updated_at") or ""), reverse=True)
    return rows[: max(1, min(50, limit))]


def _diagnosis() -> str:
    v3 = _read("data/newsroom_v3_production_status.json", {})
    v3 = v3 if isinstance(v3, dict) else {}
    settings, _ = _settings()
    state = _read("state.json", {})
    state = state if isinstance(state, dict) else {}
    limit = int(v3.get("daily_limit") or settings.get("daily_limit") or 35)
    published = int(v3.get("daily_published") or state.get("daily_published") or 0)
    remaining = max(0, int(v3.get("daily_remaining") if v3.get("daily_remaining") is not None else limit - published))
    waiting = int(v3.get("waiting") or 0)
    ready = int(v3.get("ready") or 0)
    failed_sources = int(v3.get("sources_failed") or state.get("last_sources_failed") or 0)
    publish_failed = int(v3.get("publish_failed") or 0)
    reason = str(v3.get("reason") or state.get("last_reason") or "نامشخص")
    telegram = str(state.get("telegram_state") or "نامشخص")
    return (
        f"امروز {published} خبر از سهمیه {limit} منتشر شده و {remaining} خبر تا سقف عادی باقی مانده. "
        f"الان {ready} خبر ready و {waiting} خبر waiting است. "
        f"منابع خطادار: {failed_sources}، خطای انتشار: {publish_failed}، وضعیت Telegram: {telegram}. "
        f"علت ثبت‌شده آخر: {reason}."
    )


def _parse_quota(message: str) -> int | None:
    normalized = message.translate(_PERSIAN_DIGITS)
    if "سهمیه" not in normalized:
        return None
    numbers = [int(value) for value in re.findall(r"\d{1,3}", normalized)]
    if not numbers:
        return None
    target = numbers[-1]
    return target if 0 <= target <= 200 else None


def _parse_source_action(message: str) -> tuple[str, str] | None:
    normalized = re.sub(r"\s+", " ", message).strip()
    if "خاموش" in normalized or "غیرفعال" in normalized:
        action = "disable_source"
        marker = "خاموش" if "خاموش" in normalized else "غیرفعال"
    elif "روشن" in normalized or "فعال" in normalized:
        action = "enable_source"
        marker = "روشن" if "روشن" in normalized else "فعال"
    else:
        return None
    name = normalized.split(marker, 1)[0].replace("رو", " ").strip(" ،,:؛")
    name = re.sub(r"^(منبع|سورس)\s+", "", name).strip()
    return (action, name) if name else None


def _execute_pending(record: dict) -> tuple[bool, str]:
    action = str(record.get("action") or "")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    if action == "update_daily_quota":
        target = int(payload.get("daily_limit") or 0)
        before, _ = _settings()
        previous = int(before.get("daily_limit") or 35)
        _write_settings(lambda value: {**value, "daily_limit": target})
        _audit(action, "newsroom_settings", before={"daily_limit": previous}, after={"daily_limit": target})
        return True, f"سهمیه خبر عادی از {previous} به {target} تغییر کرد."

    if action in {"disable_source", "enable_source"}:
        name = str(payload.get("name") or "").strip()
        desired = action == "enable_source"
        changed = {"before": None, "after": desired, "name": name}

        def transform(rows: list[dict]) -> list[dict]:
            matched = False
            for row in rows:
                candidates = {str(row.get("name") or "").casefold(), str(row.get("handle") or "").lstrip("@").casefold(), str(row.get("id") or "").casefold()}
                if name.casefold().lstrip("@") in candidates:
                    changed["before"] = bool(row.get("active", True))
                    row["active"] = desired
                    row["updated_at"] = _now_iso()
                    matched = True
                    break
            if not matched:
                raise ValueError("source_not_found")
            return rows

        try:
            _write_list("data/custom_sources.json", transform, "panel v4: assistant source toggle")
        except ValueError:
            return False, f"منبع «{name}» در منابع قابل‌مدیریت پنل پیدا نشد."
        _audit(action, name, before={"active": changed["before"]}, after={"active": desired})
        return True, f"منبع «{name}» {'فعال' if desired else 'غیرفعال'} شد."

    return False, "این اکشن دیگر معتبر نیست."


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.post("/api/panel/luna/assistant")
def assistant():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "empty_message", "message": "پیام خالی است"}), 400

    quota = _parse_quota(message)
    if quota is not None:
        action_id = _save_pending("update_daily_quota", {"daily_limit": quota}, f"سهمیه خبر عادی روی {quota} تنظیم شود؟")
        return jsonify({
            "ok": True,
            "action": "update_daily_quota",
            "confirmation_required": True,
            "action_id": action_id,
            "reply_fa": f"سهمیه خبر عادی را روی {quota} بگذارم؟ این تغییر فقط بعد از تأیید تو اعمال می‌شود.",
        })

    source_action = _parse_source_action(message)
    if source_action:
        action, name = source_action
        action_id = _save_pending(action, {"name": name}, f"منبع {name} تغییر وضعیت بدهد؟")
        return jsonify({
            "ok": True,
            "action": action,
            "confirmation_required": True,
            "action_id": action_id,
            "reply_fa": f"می‌خواهی منبع «{name}» {'فعال' if action == 'enable_source' else 'غیرفعال'} شود؟ بعد از تأیید اجرا می‌کنم.",
        })

    if ("آخرین" in message or "اخیر" in message) and ("خبر" in message or "منتشر" in message):
        normalized = message.translate(_PERSIAN_DIGITS)
        match = re.search(r"\d{1,2}", normalized)
        limit = max(1, min(50, int(match.group()) if match else 20))
        rows = _published_rows(limit)
        if not rows:
            reply = "در آرشیو پنل خبر منتشرشده‌ای پیدا نکردم."
        else:
            lines = []
            for index, row in enumerate(rows, 1):
                title = str(row.get("final_persian_title") or row.get("persian_title") or row.get("title") or "بدون عنوان").strip()
                lines.append(f"{index}. {title}")
            reply = "آخرین خبرهای منتشرشده:\n" + "\n".join(lines)
        return jsonify({"ok": True, "action": "list_recent_published", "confirmation_required": False, "reply_fa": reply})

    if any(term in message for term in ("چرا", "کم منتشر", "خبر کم", "سکوت", "منتشر نشده", "منتشر نشد")):
        return jsonify({"ok": True, "action": "diagnose", "confirmation_required": False, "reply_fa": _diagnosis()})

    return jsonify({
        "ok": True,
        "action": "help",
        "confirmation_required": False,
        "reply_fa": "می‌توانم علت کم‌بودن انتشار را بررسی کنم، آخرین خبرهای منتشرشده را نشان بدهم، سهمیه روزانه را با تأیید تو تغییر بدهم، یا یک منبع قابل‌مدیریت را روشن/خاموش کنم.",
    })


@bp.post("/api/panel/luna/assistant/confirm/<action_id>")
def confirm_action(action_id: str):
    pending = _rows("data/panel_pending_actions.json")
    record = next((row for row in pending if str(row.get("id") or "") == action_id and str(row.get("status") or "") == "pending"), None)
    if record is None:
        return jsonify({"ok": False, "error": "pending_action_not_found", "message": "این درخواست تأیید دیگر معتبر نیست"}), 404
    ok, reply = _execute_pending(record)
    new_status = "completed" if ok else "failed"
    now = _now_iso()

    def transform(rows: list[dict]) -> list[dict]:
        for row in rows:
            if str(row.get("id") or "") == action_id:
                row["status"] = new_status
                row["completed_at"] = now
                row["result"] = reply
                break
        return rows

    _write_list("data/panel_pending_actions.json", transform, "panel v4: complete assistant action")
    return jsonify({"ok": ok, "action": record.get("action"), "reply_fa": reply}), (200 if ok else 409)
