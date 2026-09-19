from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import requests
from flask import Blueprint, current_app, jsonify, request, session

from .command_center import _enqueue
from .github_builder import BuilderError
from .github_builder_release import BuilderRelease, configured_builder
from .luna_builder import is_builder_request
from .luna_capabilities import build_capability_registry
from .luna_context import LunaContextResolver
from .luna_control_runtime import LunaControlRuntime
from .luna_conversation import LunaConversationStore
from .luna_proposals import ProposalStore
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
برای اطلاعات و عملیات اتاق خبر فقط از قابلیت‌های تعریف‌شده استفاده کن و هرگز وانمود نکن کاری انجام شده مگر نتیجه executor موفق باشد.
خواندن و بررسی را می‌توانی مستقیم انجام بدهی. هر عملیاتی که داده، منبع، خبر، تنظیمات، کد، UI یا وضعیت انتشار را تغییر می‌دهد باید ابتدا proposal دقیق بسازد و منتظر تأیید کاربر بماند.
اگر کاربر می‌گوید «این خبر»، «همین منبع» یا مرجع مشابه، از context ساختاریافته استفاده کن؛ اگر هدف مبهم بود سؤال کوتاه بپرس و حدس نزن.
برای تغییر نام منبع از rename_source، برای فقط-بررسی از set_source_review_only و برای صدای خبر جدید از set_newsroom_alarm استفاده کن.
برای انتشار، copy_mode را مشخص کن: machine برای ترجمه ماشینی، luna برای نسخه Luna.
ترجمه خبر فقط ترجمه/ویرایش خبری است؛ بدون امتیازدهی و نظر سیاسی.
برای تغییر خود پنل، UI، ماژول یا کد از builder_prepare استفاده کن؛ Builder روی branch جدا کار می‌کند و merge فقط بعد از CI سبز و تأیید جداگانه ممکن است.
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


class _ConfiguredBuilderProxy:
    """Delay token/config validation until a confirmed Builder action executes."""

    def start_change(self, request_text: str):
        return configured_builder().start_change(request_text)


def _builder_release():
    return BuilderRelease(configured_builder())


def _control_runtime(*, provider_client=None) -> LunaControlRuntime:
    toolbox = LunaToolbox(_data())
    return LunaControlRuntime(
        registry=build_capability_registry(),
        toolbox=toolbox,
        resolver=LunaContextResolver(toolbox),
        proposals=ProposalStore(_data(), ttl_minutes=_PENDING_TTL_MINUTES),
        provider_client=provider_client,
        enqueue=_enqueue,
        builder=_ConfiguredBuilderProxy(),
        builder_release_factory=_builder_release,
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


def _update_context_from_result(store: LunaConversationStore, conversation_id: str, result: dict) -> None:
    values = {}
    target = result.get("target") if isinstance(result.get("target"), dict) else {}
    if target.get("type") == "story" and target.get("id"):
        values["last_story_id"] = str(target["id"])
    if target.get("type") == "source" and target.get("id") and target.get("id") != "new":
        values["last_source_id"] = str(target["id"])
    if result.get("action_id"):
        values["last_action_id"] = str(result["action_id"])
    story = result.get("story") if isinstance(result.get("story"), dict) else {}
    source = result.get("source") if isinstance(result.get("source"), dict) else {}
    if story.get("id"):
        values["last_story_id"] = str(story["id"])
    if source.get("id"):
        values["last_source_id"] = str(source["id"])
    if result.get("pr_number"):
        values["last_builder_pr"] = int(result["pr_number"])
    if values:
        store.update_context(conversation_id, **values)


def _legacy_finish_pending(action_id: str, *, status: str, result: dict) -> None:
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
    _mutate("data/panel_pending_actions.json", [], transform, "panel v4.2: complete legacy Luna action")


def _legacy_confirm(record: dict, action_id: str):
    action_type = str(record.get("action") or "")
    if action_type == "builder_prepare":
        request_text = str((record.get("payload") or {}).get("request") or "").strip()
        try:
            result = configured_builder().start_change(request_text)
        except BuilderError as exc:
            result = {"ok": False, "error": "builder_failed", "message": str(exc)}
        except LunaProviderError as exc:
            result = {"ok": False, "error": exc.code, "message": exc.message_fa}
        _legacy_finish_pending(action_id, status="completed" if result.get("ok") else "failed", result=result)
        return jsonify(result), (200 if result.get("ok") else 409)
    if action_type != "operator_tool":
        return jsonify({"ok": False, "error": "invalid_pending_action", "message": "این عملیات دیگر معتبر نیست."}), 409
    tool_name = str(record.get("tool_name") or "")
    arguments = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    result = execute_luna_tool(LunaToolbox(_data()), tool_name, arguments, confirmed=True)
    _legacy_finish_pending(action_id, status="completed" if result.get("ok") else "failed", result=result)
    return jsonify(result), (200 if result.get("ok") else 409)


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

    conversation_id = _conversation_id()
    store = _conversation_store()
    context = store.get_context(conversation_id)

    # Code/UI requests do not need an extra model round just to discover Builder.
    if is_builder_request(message) and image is None:
        result = _control_runtime().invoke("builder_prepare", {"request": message}, context)
        _update_context_from_result(store, conversation_id, result)
        reply = str(result.get("summary_fa") or result.get("message") or "درخواست Builder آماده بررسی است.")
        store.append(conversation_id, "user", message)
        store.append(conversation_id, "assistant", reply)
        return jsonify({
            "ok": bool(result.get("ok")),
            "mode": "builder",
            "reply_fa": reply,
            "confirmation_required": bool(result.get("confirmation_required")),
            **{key: result[key] for key in ("action_id", "summary_fa", "target", "before", "after") if key in result},
        })

    content = [{"type": "input_text", "text": message or "این تصویر را بررسی کن."}]
    if image is not None:
        content.append(image)
    input_items = _history_input(store, conversation_id)
    input_items.append({"role": "user", "content": content})

    client = get_luna_client()
    runtime = _control_runtime(provider_client=client)
    tools = tool_schemas()
    pending = None
    events = []
    reply = ""
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
                reply = client.output_text(response).strip()
                break
            outputs = []
            for call in calls:
                result = runtime.invoke(call["name"], call["arguments"], context)
                _update_context_from_result(store, conversation_id, result)
                event = {
                    "tool": call["name"],
                    "ok": bool(result.get("ok")),
                    "message": str(result.get("message") or result.get("summary_fa") or ""),
                }
                if result.get("confirmation_required"):
                    pending = {
                        "action_id": str(result.get("action_id") or ""),
                        "tool": call["name"],
                        "summary_fa": str(result.get("summary_fa") or "این عملیات اجرا شود؟"),
                    }
                    event["confirmation_required"] = True
                    events.append(event)
                    reply = pending["summary_fa"]
                    break
                events.append(event)
                outputs.append({
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": json.dumps(result, ensure_ascii=False),
                })
            if pending:
                break
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
        if not reply and not pending:
            reply = client.output_text(response).strip()
    except LunaProviderError as exc:
        return _provider_error(exc)

    if not reply:
        if pending:
            reply = pending["summary_fa"]
        elif events and events[-1].get("ok"):
            reply = events[-1].get("message") or "عملیات با موفقیت اجرا شد."
        else:
            reply = "نتیجه قابل تأییدی نگرفتم؛ کوتاه‌تر بگو چه کاری انجام بدهم."
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
    store = ProposalStore(_data(), ttl_minutes=_PENDING_TTL_MINUTES)
    record = store.get_pending(action_id)
    if record.get("status") == "missing":
        return jsonify({"ok": False, "error": "pending_action_not_found", "message": "این تأیید دیگر معتبر نیست."}), 404

    # Existing pre-v4.2 pending records remain confirmable during rollout.
    if not record.get("capability"):
        if record.get("status") != "pending":
            return jsonify({"ok": False, "error": "pending_action_not_found", "message": "این تأیید دیگر معتبر نیست."}), 404
        return _legacy_confirm(record, action_id)

    if record.get("status") == "expired":
        return jsonify({"ok": False, "error": "confirmation_expired", "message": "زمان این تأیید تمام شده؛ درخواست را دوباره به Luna بگو."}), 410
    if record.get("status") != "pending":
        return jsonify({"ok": False, "error": "proposal_not_pending", "message": "این تأیید قبلاً مصرف شده یا دیگر معتبر نیست."}), 409

    provider_client = None
    if str(record.get("capability") or "") == "translate_story":
        try:
            provider_client = get_luna_client()
        except LunaProviderError as exc:
            return _provider_error(exc)
    try:
        result = _control_runtime(provider_client=provider_client).confirm(action_id)
    except BuilderError as exc:
        result = {"ok": False, "error": "builder_failed", "message": str(exc)}
    except LunaProviderError as exc:
        return _provider_error(exc)

    conversation_id = _conversation_id()
    _update_context_from_result(_conversation_store(), conversation_id, result)
    if result.get("ok"):
        return jsonify(result), 200
    error = str(result.get("error") or "")
    status = 410 if error in {"proposal_expired", "confirmation_expired"} else 409
    return jsonify(result), status
