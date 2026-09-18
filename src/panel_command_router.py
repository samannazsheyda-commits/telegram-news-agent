from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ai_newsroom import AIServiceError
from .newsroom_v3.manual_publish import publish_manual_story
from .one_x_ai_newsroom import OneXAINewsAI
from .panel_command_file import apply_command as apply_legacy_command
from .strict_translation import _natural_persian_copy

TERMINAL = {"succeeded", "failed", "reconciled", "ambiguous"}
NEWSROOM_ACTIONS = {
    "clear", "settings_save", "publish", "v3_publish", "v3_prepare", "v3_publish_prepared",
    "weather_now", "air_traffic_now", "tanker_now", "market_now",
    "weather_preview", "air_traffic_preview", "tanker_preview", "market_preview",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _result_path(command_id: str) -> Path:
    return Path("panel_results") / f"{command_id}.json"


def _write_result(
    command_id: str,
    action: str,
    status: str,
    message: str,
    *,
    scope: str = "",
    ids: list[str] | None = None,
    item_id: str = "",
    story_id: str = "",
    telegram_message_id: int | None = None,
    error: str = "",
    title: str = "",
    body: str = "",
) -> dict:
    payload = {
        "command_id": command_id,
        "item_id": item_id,
        "action": action,
        "status": status,
        "message": message,
        "scope": scope,
        "ids": list(ids or []),
        "story_id": story_id,
        "telegram_message_id": telegram_message_id,
        "error": error,
        "title": title,
        "body": body,
        "updated_at": _now(),
    }
    _atomic_write(_result_path(command_id), payload)
    return payload


def _consume(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _command_payload(path: Path) -> dict[str, Any]:
    payload = _read_json(path, None)
    if not isinstance(payload, dict):
        raise ValueError("invalid_command")
    command_id = str(payload.get("command_id") or path.stem).strip()
    action = str(payload.get("action") or "").strip()
    if not command_id:
        raise ValueError("missing_command_id")
    if not action:
        raise ValueError("missing_action")
    payload["command_id"] = command_id
    payload["action"] = action
    return payload


def _validated_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("ids_must_be_list")
    ids: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item_id = str(raw or "").strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        ids.append(item_id)
    if len(ids) > 5000:
        raise ValueError("too_many_ids")
    return ids


def _row_id(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("id") or row.get("item_id") or row.get("news_key") or "").strip()


def _clear_live(ids: list[str]) -> int:
    path = Path("data/panel_live_feed.json")
    targets = set(ids)
    before = _read_json(path, [])
    if not isinstance(before, list):
        before = []
    after = [row for row in before if _row_id(row) not in targets]
    removed = len(before) - len(after)
    if removed:
        _atomic_write(path, after)
    return removed


def _apply_clear(payload: dict[str, Any]) -> dict:
    command_id = payload["command_id"]
    scope = str(payload.get("scope") or "").strip()
    ids = _validated_ids(payload.get("ids"))
    if scope != "live":
        raise ValueError("invalid_clear_scope")
    count = _clear_live(ids)
    return _write_result(command_id, "clear", "succeeded", f"{count} خبر فقط از فید پنل پاک شد؛ تلگرام دست‌نخورده ماند", scope=scope, ids=ids)


def _normalise_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("settings_must_be_object")
    settings = dict(value)
    settings["updated_at"] = _now()
    settings["version"] = int(settings.get("version") or 1)
    settings["freshness_hours"] = max(1, min(48, int(settings.get("freshness_hours") or 3)))
    settings["daily_limit"] = max(1, min(100, int(settings.get("daily_limit") or 35)))
    settings["special_limit"] = max(0, min(10, int(settings.get("special_limit") or 5)))
    settings["earthquake_min"] = max(0.0, min(10.0, float(settings.get("earthquake_min") or 2.0)))
    settings["earthquake_breaking"] = max(settings["earthquake_min"], min(10.0, float(settings.get("earthquake_breaking") or 4.0)))
    if settings.get("dedup_mode") not in {"strict", "balanced", "loose"}:
        settings["dedup_mode"] = "strict"
    if settings.get("notam_sensitivity") not in {"high", "normal", "critical"}:
        settings["notam_sensitivity"] = "high"
    settings["emergency_lock"] = bool(settings.get("emergency_lock", False))
    settings["auto_publish"] = bool(settings.get("auto_publish", True))
    settings["quiet_mode"] = bool(settings.get("quiet_mode", False))
    priority_terms = settings.get("priority_terms")
    settings["priority_terms"] = [str(term).strip() for term in priority_terms if str(term).strip()][:20] if isinstance(priority_terms, list) else []
    for key in ("market", "alerts", "ui", "sources"):
        if not isinstance(settings.get(key), dict):
            settings[key] = {}
    return settings


def _apply_settings(payload: dict[str, Any]) -> dict:
    settings = _normalise_settings(payload.get("settings"))
    _atomic_write(Path("data/newsroom_settings.json"), settings)
    return _write_result(payload["command_id"], "settings_save", "succeeded", "تنظیمات اتاق خبر ذخیره شد")


def _save_preview(name: str, preview: dict) -> None:
    if not isinstance(preview, dict):
        raise ValueError("invalid_preview")
    _atomic_write(Path("data") / f"{name}_preview.json", preview)


def _apply_module(payload: dict[str, Any]) -> dict:
    action = payload["action"]
    command_id = payload["command_id"]
    if action == "weather_preview":
        from .weather_digest import build_preview, save_preview
        preview = build_preview(); save_preview(preview); _save_preview("weather", preview)
        return _write_result(command_id, action, "succeeded", "پیش‌نمایش هواشناسی به‌روز شد؛ چیزی منتشر نشد")
    if action == "air_traffic_preview":
        from .air_traffic import build_air_traffic_preview
        preview = build_air_traffic_preview(); _save_preview("air_traffic", preview)
        return _write_result(command_id, action, "succeeded", "پیش‌نمایش ترافیک هوایی به‌روز شد؛ چیزی منتشر نشد")
    if action == "tanker_preview":
        from .panel_modules import build_hormuz_preview
        preview = build_hormuz_preview(); _save_preview("tanker", preview)
        return _write_result(command_id, action, "succeeded", "پیش‌نمایش هرمز به‌روز شد؛ چیزی منتشر نشد")
    if action == "market_preview":
        from .panel_modules import build_market_preview
        preview = build_market_preview(); _save_preview("market", preview)
        return _write_result(command_id, action, "succeeded", "پیش‌نمایش بازار به‌روز شد؛ چیزی منتشر نشد")
    if action == "weather_now":
        from .weather_digest import run as run_weather
        rc = int(run_weather(force=True) or 0)
        if rc != 0: raise RuntimeError(f"weather_failed_rc_{rc}")
        return _write_result(command_id, action, "succeeded", "هواشناسی همین حالا منتشر شد")
    if action == "air_traffic_now":
        from .air_traffic import publish_air_traffic_snapshot
        publish_air_traffic_snapshot()
        return _write_result(command_id, action, "succeeded", "نقشه ترافیک هوایی همین حالا منتشر شد")
    if action == "tanker_now":
        from .panel_modules import publish_hormuz_now
        publish_hormuz_now()
        return _write_result(command_id, action, "succeeded", "گزارش نفتکش‌ها و تنگه هرمز منتشر شد")
    if action == "market_now":
        from .panel_modules import publish_market_now
        publish_market_now()
        return _write_result(command_id, action, "succeeded", "گزارش بازار همین حالا منتشر شد")
    raise ValueError("unsupported_module_action")


def _has_persian(value: str) -> bool:
    return any("\u0600" <= char <= "\u06ff" for char in str(value or ""))


def _luna_finalize_piece(ai: OneXAINewsAI, source_text: str) -> str:
    source = str(source_text or "").strip()
    if not source:
        return ""
    if _has_persian(source):
        draft_text = source
    else:
        draft = ai.translate_to_fa(source)
        draft_text = str(getattr(draft, "text", "") or "").strip()
        if not draft_text or getattr(draft, "faithful", False) is not True:
            raise AIServiceError("luna_manual_translation_rejected")
    edit = ai.edit_persian(source, draft_text)
    if getattr(edit, "faithful", False) is not True or getattr(edit, "natural", False) is not True:
        raise AIServiceError("luna_manual_edit_rejected")
    edited_text = str(getattr(edit, "text", "") or "").strip()
    if not edited_text:
        raise AIServiceError("luna_manual_edit_empty")
    guarded = _natural_persian_copy(source, edited_text)
    if not guarded or not _has_persian(guarded):
        raise AIServiceError("luna_manual_guard_rejected")
    return guarded


def _finalize_manual_copy_with_luna(original_title: str, original_body: str) -> tuple[str, str]:
    source_title = str(original_title or "").strip()
    source_body = str(original_body or "").strip()
    if not source_title:
        raise AIServiceError("missing_original_title")
    ai = OneXAINewsAI()
    if not ai.available:
        raise AIServiceError("luna_manual_unavailable")
    final_title = _luna_finalize_piece(ai, source_title)
    final_body = _luna_finalize_piece(ai, source_body) if source_body else ""
    return final_title, final_body


def _queue_row(item_id: str) -> dict:
    queue = _read_json(Path("data/editorial_queue.json"), [])
    if not isinstance(queue, list):
        return {}
    return next((dict(row) for row in queue if isinstance(row, dict) and _row_id(row) == item_id), {})


def _save_luna_preview(item_id: str, title: str, body: str) -> None:
    path = Path("data/editorial_queue.json")
    queue = _read_json(path, [])
    queue = [dict(row) for row in queue if isinstance(row, dict)] if isinstance(queue, list) else []
    now = _now()
    updated = False
    for row in queue:
        if _row_id(row) == item_id:
            row.update(
                final_persian_title=title,
                final_persian_body=body,
                luna_preview_title=title,
                luna_preview_body=body,
                luna_preview_at=now,
                status="luna_ready",
                updated_at=now,
            )
            updated = True
            break
    if not updated:
        queue.insert(0, {
            "id": item_id,
            "item_id": item_id,
            "final_persian_title": title,
            "final_persian_body": body,
            "luna_preview_title": title,
            "luna_preview_body": body,
            "luna_preview_at": now,
            "status": "luna_ready",
            "updated_at": now,
        })
    _atomic_write(path, queue)


def _story_context(payload: dict[str, Any]) -> dict[str, str]:
    item_id = str(payload.get("item_id") or "").strip()
    if not item_id:
        raise ValueError("missing_item_id")
    queued = _queue_row(item_id)
    source = str(payload.get("source") or queued.get("source") or "").strip()
    source_url = str(payload.get("source_url") or queued.get("source_url") or "").strip()
    original_title = str(payload.get("original_title") or queued.get("original_title") or queued.get("title") or "").strip()
    original_body = str(payload.get("original_body") or queued.get("original_summary") or queued.get("summary") or queued.get("body") or "").strip()
    news_key = str(payload.get("news_key") or queued.get("news_key") or item_id).strip()
    published_at = str(payload.get("published_at") or queued.get("published_at_source") or "").strip()
    if not source or not source_url:
        raise ValueError("missing_source")
    if not original_title:
        raise ValueError("missing_original_title")
    return {
        "item_id": item_id,
        "source": source,
        "source_url": source_url,
        "original_title": original_title,
        "original_body": original_body,
        "news_key": news_key,
        "published_at": published_at,
    }


def _apply_v3_prepare(payload: dict[str, Any]) -> dict:
    context = _story_context(payload)
    title, body = _finalize_manual_copy_with_luna(context["original_title"], context["original_body"])
    _save_luna_preview(context["item_id"], title, body)
    return _write_result(
        payload["command_id"],
        "v3_prepare",
        "succeeded",
        "نسخه نهایی لونا آماده شد؛ هنوز چیزی منتشر نشده",
        item_id=context["item_id"],
        title=title,
        body=body,
    )


def _finalize_editorial_publish(payload: dict[str, Any], result: dict) -> None:
    item_id = str(payload.get("item_id") or "").strip()
    queue_path = Path("data/editorial_queue.json")
    history_path = Path("data/editorial_history.json")
    live_path = Path("data/panel_live_feed.json")
    queue = _read_json(queue_path, [])
    queue = [dict(row) for row in queue if isinstance(row, dict)] if isinstance(queue, list) else []
    current = next((row for row in queue if _row_id(row) == item_id), None)
    if current is None:
        current = {"id": item_id, "item_id": item_id, "news_key": str(payload.get("news_key") or item_id), "source": str(payload.get("source") or ""), "source_url": str(payload.get("source_url") or ""), "persian_title": str(payload.get("title") or ""), "persian_body": str(payload.get("body") or "")}
    now = _now()
    final = dict(current)
    final.update(status="published_manual", final_persian_title=str(payload.get("title") or current.get("persian_title") or ""), final_persian_body=str(payload.get("body") or current.get("persian_body") or ""), decision_at=now, updated_at=now, telegram_message_id=result.get("telegram_message_id"), v3_story_id=str(result.get("story_id") or ""))
    _atomic_write(queue_path, [row for row in queue if _row_id(row) != item_id])
    history = _read_json(history_path, [])
    history = [dict(row) for row in history if isinstance(row, dict)] if isinstance(history, list) else []
    _atomic_write(history_path, [final] + [row for row in history if _row_id(row) != item_id])
    live = _read_json(live_path, [])
    if isinstance(live, list):
        _atomic_write(live_path, [row for row in live if _row_id(row) != item_id])


def _publish_prepared(payload: dict[str, Any], *, action: str) -> dict:
    context = _story_context(payload)
    queued = _queue_row(context["item_id"])
    title = str(payload.get("title") or queued.get("final_persian_title") or queued.get("luna_preview_title") or "").strip()
    body = str(payload.get("body") or queued.get("final_persian_body") or queued.get("luna_preview_body") or "").strip()
    if not title or not _has_persian(title):
        raise ValueError("luna_preview_required")
    result = publish_manual_story(
        data_dir=Path(os.environ.get("DATA_DIR", "data")),
        item_id=context["item_id"],
        news_key=context["news_key"],
        source=context["source"],
        source_url=context["source_url"],
        title=title,
        body=body,
        published_at=context["published_at"],
    )
    normalized = {**payload, **context, "title": title, "body": body}
    status = str(result.get("status") or "failed")
    if status in {"succeeded", "reconciled"}:
        _finalize_editorial_publish(normalized, result)
    messages = {
        "succeeded": "نسخه تأییدشده لونا با مسیر امن V3 منتشر شد",
        "reconciled": "انتشار قبلی V3 تأیید و همگام شد",
        "ambiguous": "وضعیت ارسال تلگرام نامشخص است؛ دوباره منتشر نکن",
        "processing": "انتشار V3 در حال پردازش است",
        "failed": "انتشار V3 ناموفق بود",
    }
    return _write_result(
        payload["command_id"], action, status, messages.get(status, "وضعیت انتشار V3 ثبت شد"),
        item_id=context["item_id"], story_id=str(result.get("story_id") or ""),
        telegram_message_id=result.get("telegram_message_id") if isinstance(result.get("telegram_message_id"), int) else None,
        error=str(result.get("error") or ""), title=title, body=body,
    )


def _apply_v3_publish(payload: dict[str, Any]) -> dict:
    context = _story_context(payload)
    title, body = _finalize_manual_copy_with_luna(context["original_title"], context["original_body"])
    return _publish_prepared({**payload, **context, "title": title, "body": body}, action="v3_publish")


def _apply_v3_publish_prepared(payload: dict[str, Any]) -> dict:
    return _publish_prepared(payload, action="v3_publish_prepared")


def apply_command(path: str | Path) -> dict:
    command_path = Path(path)
    if not command_path.exists():
        existing = _read_json(_result_path(command_path.stem), None)
        if isinstance(existing, dict) and existing.get("status") in TERMINAL:
            return existing
        raise FileNotFoundError(command_path)
    payload = _command_payload(command_path)
    action = payload["action"]
    if action not in NEWSROOM_ACTIONS:
        return apply_legacy_command(command_path)
    existing = _read_json(_result_path(payload["command_id"]), None)
    if isinstance(existing, dict) and existing.get("status") in TERMINAL:
        _consume(command_path)
        return existing
    _write_result(payload["command_id"], action, "processing", "در حال پردازش", item_id=str(payload.get("item_id") or ""))
    try:
        if action == "clear":
            result = _apply_clear(payload)
        elif action == "settings_save":
            result = _apply_settings(payload)
        elif action == "v3_prepare":
            result = _apply_v3_prepare(payload)
        elif action == "v3_publish_prepared":
            result = _apply_v3_publish_prepared(payload)
        elif action in {"publish", "v3_publish"}:
            result = _apply_v3_publish(payload)
        else:
            result = _apply_module(payload)
        _consume(command_path)
        return result
    except Exception as exc:
        result = _write_result(payload["command_id"], action, "failed", str(exc), scope=str(payload.get("scope") or ""), ids=list(payload.get("ids") or []), item_id=str(payload.get("item_id") or ""), error=str(exc))
        _consume(command_path)
        return result


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m src.panel_command_router <command.json>")
    result = apply_command(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False))
    if result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
