from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import requests
from flask import Blueprint, current_app, jsonify, request, session

from .github_builder import BuilderError
from .github_builder_release import configured_builder
from .luna_builder import is_builder_request
from .luna_builder_tools import builder_tool_schemas
from .luna_conversation import LunaConversationStore
from .luna_tool_runtime import execute_luna_tool
from .luna_tools import LunaToolbox, tool_schemas
from .openai_luna import LunaProviderError, get_luna_client


bp = Blueprint("luna_operator_api", __name__)
_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_TOOL_ROUNDS = 4
_PENDING_TTL_MINUTES = 15

_SYSTEM = """تو Luna، دستیار عملیاتی فارسی اتاق خبر بی‌خبر هستی.
با کاربر طبیعی و روان فارسی حرف بزن و از متن‌های کلیشه‌ای دوری کن.
برای اطلاعات و عملیات اتاق خبر حتماً از ابزارهای تعریف‌شده استفاده کن و هرگز وانمود نکن کاری انجام شده مگر نتیجه ابزار ok باشد.
اگر کاربر می‌گوید «این خبر»، «همین منبع» یا مرجع مشابه و هدف از زمینه مکالمه روشن نیست، با ابزار جست‌وجو بررسی کن؛ اگر چند گزینه محتمل بود یک سؤال کوتاه برای رفع ابهام بپرس.
عملیات حذف/مسدودسازی خبر و تغییر منبع باید به مرحله تأیید برسد؛ نتیجه confirmation_required یعنی هنوز هیچ تغییر حساسی اجرا نشده است.
ترجمه خبر باید فقط ترجمه/ویرایش خبری باشد، بدون امتیازدهی، نظر سیاسی یا پیشنهاد PUBLISH/REJECT و باید از ابزار translate_story استفاده کند.
برای تغییر خود پنل، UI، ماژول یا کد، Builder branch/PR می‌سازد. برای وضعیت تغییر از builder_ci_status استفاده کن و فقط با builder_prepare_merge و تأیید کاربر می‌توانی تغییر دارای CI سبز را merge کنی.
هرگز merge/deploy را موفق اعلام نکن مگر ابزار نتیجه موفق بدهد.
جواب نهایی را مختصر، دقیق و عملیاتی بنویس."""


def _data():
    return current_app.extensions["editorial_data"]


def _mutate(path: str, default, transform, message: str):
    data = _data()
    for attempt in range(3):
        value, sha = data.read_json(path, default)
        updated = transform(value)
        try:
            data.write_json(path, updated, sha, message)
            return updated
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt < 2 and status in {409, 422}:
                continue
            raise
    raise RuntimeError("luna_operator_write_conflict")


def _rows(path: str) -> list[dict]:
    value, _ = _data().read_json(path, [])
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _conversation_id() -> str:
    value = str(session.get("luna_conversation_id") or "").strip()
    if not value:
        value = uuid4().hex
        session["luna_conversation_id"] = value
    return value


def _conversation_store() -> LunaConversationStore:
    configured = str(os.environ.get("LUNA_CONVERSATION_PATH") or "").strip()
    if configured:
        path = configured
    elif current_app.config.get("TESTING"):
        path = "/tmp/bikhabar-luna-conversations-test.json"
    else:
        path = "/var/lib/bikhabar/luna_conversations.json"
    return LunaConversationStore(path)


def _save_pending(
    tool_name: str,
    arguments: dict,
    summary_fa: str,
    *,
    action_type: str = "operator_tool",
) -> str:
    action_id = uuid4().hex
    now = datetime.now(timezone.utc)
    record = {
        "id": action_id,
        "action": action_type,
        "tool_name": str(tool_name),
        "payload": dict(arguments),
        "summary_fa": str(summary_fa or "این عملیات اجرا شود؟"),
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=_PENDING_TTL_MINUTES)).isoformat(),
    }
    _mutate(
        "data/panel_pending_actions.json",
        [],
        lambda rows: ([record] + [dict(row) for row in list(rows or []) if isinstance(row, dict)])[:100],
        "panel v4.1: Luna pending action",
    )
    return action_id


def _finish_pending(action_id: str, *, status: str, result: dict) -> None:
    def transform(rows):
        output = []
        for raw in list(rows or []):
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            if str(row.get("id") or "") == action_id:
                row["status"] = status
                row["result"] = dict(result)
                row["completed_at"] = datetime.now(timezone.utc).isoformat()
            output.append(row)
        return output
    _mutate("data/panel_pending_actions.json", [], transform, "panel v4.1: complete Luna action")


def _expired(record: dict) -> bool:
    raw = str(record.get("expires_at") or "").strip()
    if not raw:
        return False
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except ValueError:
        return True


def _audit(action: str, status: str, summary: str, result: dict | None = None) -> None:
    record = {
        "id": uuid4().hex,
        "at": datetime.now(timezone.utc).isoformat(),
        "actor": "luna_operator",
        "action": str(action or ""),
        "status": str(status or ""),
        "summary": str(summary or "")[:500],
        "result": {
            key: value
            for key, value in dict(result or {}).items()
            if key in {"ok", "error", "message", "pr_number", "merge_sha", "rollback_sha"}
        },
    }
    _mutate(
        "data/panel_audit_log.json",
        [],
        lambda rows: ([record] + [dict(row) for row in list(rows or []) if isinstance(row, dict)])[:300],
        "panel v4.1: Luna audit",
    )


def _provider_error(exc: LunaProviderError):
    status = 503 if exc.retryable or exc.code in {"missing_api_key", "provider_unavailable"} else 502
    return jsonify({"ok": False, "error": exc.code, "message": exc.message_fa, "retryable": exc.retryable}), status


def _image_part(upload):
    if upload is None or not str(upload.filename or "").strip():
        return None, None
    extension = Path(str(upload.filename)).suffix.lower()
    mimetype = str(upload.mimetype or "").lower()
    if extension not in _IMAGE_EXTENSIONS or mimetype not in _IMAGE_MIMES:
        return None, (jsonify({"ok": False, "error": "unsupported_image_type", "message": "فقط JPG، PNG و WebP پشتیبانی می‌شود."}), 415)
    content = upload.read(_MAX_IMAGE_BYTES + 1)
    if not content:
        return None, (jsonify({"ok": False, "error": "empty_image", "message": "تصویر خالی است."}), 400)
    if len(content) > _MAX_IMAGE_BYTES:
        return None, (jsonify({"ok": False, "error": "image_too_large", "message": "حجم تصویر بیشتر از حد مجاز است."}), 413)
    encoded = base64.b64encode(content).decode("ascii")
    return {"type": "input_image", "image_url": f"data:{mimetype};base64,{encoded}", "detail": "auto"}, None


def _history_input(store: LunaConversationStore, conversation_id: str) -> list[dict]:
    result = []
    for row in store.recent(conversation_id):
        role = str(row.get("role") or "")
        text = str(row.get("content") or "").strip()
        if role in {"user", "assistant"} and text:
            result.append({"role": role, "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}]})
    return result


def _safe_tool_result(result: dict) -> dict:
    clean = dict(result)
    clean.pop("pending_action", None)
    return clean


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.post("/api/panel/luna/operator-chat")
def operator_chat():
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message") or "").strip()
        upload = None
    else:
        message = str(request.form.get("message") or "").strip()
        upload = request.files.get("image")
    image, image_error = _image_part(upload)
    if image_error:
        return image_error
    if not message and image is None:
        return jsonify({"ok": False, "error": "empty_message", "message": "پیام یا تصویر لازم است."}), 400

    if is_builder_request(message) and image is None:
        action_id = _save_pending(
            "builder_prepare",
            {"request": message},
            "Luna این تغییر کدنویسی را روی branch جدا بسازد، تست اضافه کند و Draft PR باز کند؟",
            action_type="builder_prepare",
        )
        return jsonify(
            {
                "ok": True,
                "mode": "builder",
                "builder_request": message,
                "confirmation_required": True,
                "action_id": action_id,
                "summary_fa": "Luna تغییر را روی branch جدا می‌سازد؛ production مستقیم دستکاری نمی‌شود.",
                "reply_fa": "این درخواست مربوط به تغییر خود پنل/کد است. آماده‌ام Builder را شروع کنم، تست بنویسم و Draft PR بسازم.",
            }
        )

    conversation_id = _conversation_id()
    store = _conversation_store()
    content = [{"type": "input_text", "text": message or "این تصویر را بررسی کن."}]
    if image is not None:
        content.append(image)
    input_items = _history_input(store, conversation_id)
    input_items.append({"role": "user", "content": content})

    client = get_luna_client()
    toolbox = LunaToolbox(_data())
    tools = tool_schemas() + builder_tool_schemas()
    pending = None
    events = []
    try:
        response = client.create_response(
            input_items=input_items,
            tools=tools,
            model=client.fast_model,
            instructions=_SYSTEM,
        )
        continuation_input = list(input_items)
        response_output = response.get("output") if isinstance(response, dict) else []
        if isinstance(response_output, list):
            continuation_input.extend(response_output)
        for _ in range(_MAX_TOOL_ROUNDS):
            calls = client.function_calls(response)
            if not calls:
                break
            outputs = []
            for call in calls:
                result = execute_luna_tool(
                    toolbox,
                    call["name"],
                    call["arguments"],
                    provider_client=client,
                )
                event = {"tool": call["name"], "ok": bool(result.get("ok")), "message": str(result.get("message") or "")}
                if result.get("confirmation_required") and isinstance(result.get("pending_action"), dict):
                    proposal = result["pending_action"]
                    action_id = _save_pending(
                        str(proposal.get("action") or call["name"]),
                        dict(proposal.get("payload") or {}),
                        str(proposal.get("summary_fa") or "این عملیات اجرا شود؟"),
                    )
                    pending = {
                        "action_id": action_id,
                        "tool": call["name"],
                        "summary_fa": str(proposal.get("summary_fa") or "این عملیات اجرا شود؟"),
                    }
                    result = {**_safe_tool_result(result), "action_id": action_id, "summary_fa": pending["summary_fa"]}
                    event["confirmation_required"] = True
                events.append(event)
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )
            continuation_input.extend(outputs)
            response = client.create_response(
                input_items=continuation_input,
                tools=tools,
                model=client.fast_model,
                instructions=_SYSTEM,
            )
            response_output = response.get("output") if isinstance(response, dict) else []
            if isinstance(response_output, list):
                continuation_input.extend(response_output)
        reply = client.output_text(response).strip()
    except LunaProviderError as exc:
        return _provider_error(exc)

    if not reply:
        reply = pending["summary_fa"] if pending else "انجام شد."
    if message:
        store.append(conversation_id, "user", message)
    store.append(conversation_id, "assistant", reply)
    payload = {
        "ok": True,
        "mode": "operator",
        "reply_fa": reply,
        "tool_events": events,
        "confirmation_required": bool(pending),
    }
    if pending:
        payload.update(pending)
    return jsonify(payload)


@bp.post("/api/panel/luna/operator-confirm/<action_id>")
def operator_confirm(action_id: str):
    record = next(
        (
            row
            for row in _rows("data/panel_pending_actions.json")
            if str(row.get("id") or "") == action_id and str(row.get("status") or "") == "pending"
        ),
        None,
    )
    if record is None:
        return jsonify({"ok": False, "error": "pending_action_not_found", "message": "این تأیید دیگر معتبر نیست."}), 404
    if _expired(record):
        result = {"ok": False, "error": "confirmation_expired", "message": "زمان این تأیید تمام شده؛ درخواست را دوباره به Luna بگو."}
        _finish_pending(action_id, status="expired", result=result)
        return jsonify(result), 410

    action_type = str(record.get("action") or "")
    if action_type == "builder_prepare":
        request_text = str((record.get("payload") or {}).get("request") or "").strip()
        try:
            result = configured_builder().start_change(request_text)
        except BuilderError as exc:
            result = {"ok": False, "error": "builder_failed", "message": str(exc)}
        except LunaProviderError as exc:
            result = {"ok": False, "error": exc.code, "message": exc.message_fa}
        _finish_pending(action_id, status="completed" if result.get("ok") else "failed", result=result)
        _audit("builder_prepare", "completed" if result.get("ok") else "failed", request_text, result)
        return jsonify(result), (200 if result.get("ok") else 409)

    if action_type != "operator_tool":
        return jsonify({"ok": False, "error": "invalid_pending_action", "message": "این عملیات دیگر معتبر نیست."}), 409

    tool_name = str(record.get("tool_name") or "")
    arguments = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    result = execute_luna_tool(
        LunaToolbox(_data()),
        tool_name,
        arguments,
        confirmed=True,
    )
    _finish_pending(action_id, status="completed" if result.get("ok") else "failed", result=result)
    _audit(tool_name, "completed" if result.get("ok") else "failed", str(record.get("summary_fa") or tool_name), result)
    return jsonify(result), (200 if result.get("ok") else 409)
