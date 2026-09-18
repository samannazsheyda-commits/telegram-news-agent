from __future__ import annotations

import json

from flask import Blueprint, current_app, jsonify, render_template, request, session

from src.ai_newsroom import AIServiceError
from src.one_x_ai_newsroom import OneXAINewsAI

from .audit_log import append_audit, list_audit
from .luna_assistant import handle_control_message


bp = Blueprint("panel_v4_assistant", __name__)


def _data():
    return current_app.extensions["editorial_data"]


def _luna_readonly_reply(message: str, context: dict) -> str:
    ai = OneXAINewsAI()
    if not ai.available:
        raise AIServiceError("luna_assistant_unavailable")
    system = (
        "تو Luna Control Assistant پنل خبری بی‌خبر هستی. "
        "فقط بر اساس CONTEXT داده‌شده پاسخ کوتاه، روشن و فارسی بده. "
        "هیچ action، انتشار، حذف، restart یا تغییر تنظیماتی انجام نده و وانمود نکن انجام داده‌ای. "
        "اگر داده برای نتیجه قطعی کافی نیست، صریح بگو نامشخص است. "
        "secret، token، API key یا اطلاعات احراز هویت را هرگز درخواست یا نمایش نده."
    )
    user = "CONTEXT:\n" + json.dumps(context, ensure_ascii=False) + "\n\nUSER:\n" + message
    reply = ai._chat_text(model=ai.config.model, system=system, user=user, max_tokens=550)
    if not reply:
        raise AIServiceError("empty_luna_assistant_reply")
    return reply


@bp.before_request
def require_admin():
    if not session.get("admin"):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        from flask import redirect, url_for
        return redirect(url_for("login", next=request.path))
    return None


@bp.post("/api/v4/assistant/message")
def assistant_message():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip() if isinstance(payload, dict) else ""
    if not message or len(message) > 1200:
        return jsonify({"ok": False, "error": "invalid_message", "message": "پیام معتبر نیست."}), 400

    data = _data()
    result = handle_control_message(data, message)
    if result.get("status") != "needs_luna":
        return jsonify({"ok": result.get("status") == "succeeded", **result})

    try:
        reply = _luna_readonly_reply(message, dict(result.get("context") or {}))
    except AIServiceError as exc:
        append_audit(
            data,
            actor="luna",
            action="assistant_chat",
            target="panel",
            before={"message": message},
            after={},
            result=f"error:{type(exc).__name__}",
        )
        return jsonify({
            "ok": False,
            "intent": "assistant_chat",
            "status": "failed",
            "error": "luna_unavailable",
            "message": "Luna فعلاً پاسخ نداد؛ وضعیت provider را در بخش سلامت بررسی کن.",
        }), 503

    append_audit(
        data,
        actor="luna",
        action="assistant_chat",
        target="panel",
        before={"message": message},
        after={"reply_fa": reply[:2000]},
        result="ok",
    )
    return jsonify({
        "ok": True,
        "intent": "assistant_chat",
        "status": "succeeded",
        "requires_confirmation": False,
        "reply_fa": reply,
    })


@bp.get("/api/v4/audit")
def audit_api():
    try:
        limit = max(1, min(200, int(request.args.get("limit", "50"))))
    except (TypeError, ValueError):
        limit = 50
    actor = str(request.args.get("actor") or "").strip()
    action = str(request.args.get("action") or "").strip()
    return jsonify({"ok": True, "items": list_audit(_data(), limit=limit, actor=actor, action=action)})


@bp.get("/audit")
def audit_page():
    rows = list_audit(_data(), limit=100)
    return render_template("audit_v4.html", items=rows)
