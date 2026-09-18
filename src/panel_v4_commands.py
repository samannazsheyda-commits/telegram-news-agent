from __future__ import annotations

from pathlib import Path
from typing import Any

from .newsroom_v3.manual_publish import publish_manual_story
from .panel_command_router import (
    _atomic_write,
    _command_payload,
    _consume,
    _finalize_editorial_publish,
    _finalize_manual_copy_with_luna,
    _now,
    _read_json,
    _result_path,
    _row_id,
    apply_command as apply_legacy_command,
)


V4_ACTIONS = {"v3_prepare", "v3_publish_prepared"}
PREPARED_PATH = Path("data/panel_luna_prepared.json")
TERMINAL = {"succeeded", "failed", "reconciled", "ambiguous"}


def _prepared_rows() -> list[dict]:
    value = _read_json(PREPARED_PATH, [])
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _prepared(item_id: str) -> dict | None:
    return next((row for row in _prepared_rows() if _row_id(row) == item_id), None)


def _save_prepared(record: dict) -> None:
    item_id = _row_id(record)
    rows = _prepared_rows()
    _atomic_write(PREPARED_PATH, [record] + [row for row in rows if _row_id(row) != item_id])


def _remove_prepared(item_id: str) -> None:
    rows = _prepared_rows()
    _atomic_write(PREPARED_PATH, [row for row in rows if _row_id(row) != item_id])


def _write_v4_result(
    command_id: str,
    action: str,
    status: str,
    message: str,
    *,
    item_id: str = "",
    story_id: str = "",
    telegram_message_id: int | None = None,
    error: str = "",
    final_title: str = "",
    final_body: str = "",
) -> dict:
    payload = {
        "command_id": command_id,
        "item_id": item_id,
        "action": action,
        "status": status,
        "message": message,
        "story_id": story_id,
        "telegram_message_id": telegram_message_id,
        "error": error,
        "final_title": final_title,
        "final_body": final_body,
        "updated_at": _now(),
    }
    _atomic_write(_result_path(command_id), payload)
    return payload


def _queue_record(item_id: str) -> dict:
    value = _read_json(Path("data/editorial_queue.json"), [])
    rows = [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    return next((row for row in rows if _row_id(row) == item_id), {})


def _source_payload(payload: dict[str, Any], queued: dict) -> dict:
    item_id = str(payload.get("item_id") or "").strip()
    source = str(payload.get("source") or queued.get("source") or "").strip()
    source_url = str(payload.get("source_url") or queued.get("source_url") or "").strip()
    original_title = str(payload.get("original_title") or queued.get("original_title") or queued.get("title") or "").strip()
    original_body = str(payload.get("original_body") or queued.get("original_summary") or queued.get("summary") or queued.get("body") or "").strip()
    news_key = str(payload.get("news_key") or queued.get("news_key") or item_id).strip()
    published_at = str(payload.get("published_at") or queued.get("published_at_source") or "").strip()
    if not item_id:
        raise ValueError("missing_item_id")
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


def _apply_prepare(payload: dict[str, Any]) -> dict:
    command_id = str(payload["command_id"])
    item_id = str(payload.get("item_id") or "").strip()
    queued = _queue_record(item_id)
    source = _source_payload(payload, queued)
    final_title, final_body = _finalize_manual_copy_with_luna(source["original_title"], source["original_body"])
    record = {
        "id": item_id,
        "item_id": item_id,
        "news_key": source["news_key"],
        "source": source["source"],
        "source_url": source["source_url"],
        "original_title": source["original_title"],
        "original_body": source["original_body"],
        "published_at": source["published_at"],
        "title": final_title,
        "body": final_body,
        "prepared_at": _now(),
    }
    _save_prepared(record)
    return _write_v4_result(
        command_id,
        "v3_prepare",
        "succeeded",
        "نسخه نهایی لونا آماده شد؛ هنوز چیزی منتشر نشده",
        item_id=item_id,
        final_title=final_title,
        final_body=final_body,
    )


def _apply_publish_prepared(payload: dict[str, Any]) -> dict:
    command_id = str(payload["command_id"])
    item_id = str(payload.get("item_id") or "").strip()
    staged = _prepared(item_id)
    if staged is None:
        raise ValueError("luna_preview_missing")

    title = str(payload.get("title") or staged.get("title") or "").strip()
    body = str(payload.get("body") or staged.get("body") or "").strip()
    if not title or not any("\u0600" <= char <= "\u06ff" for char in title):
        raise ValueError("invalid_final_title")

    result = publish_manual_story(
        data_dir=Path("data"),
        item_id=item_id,
        news_key=str(staged.get("news_key") or item_id),
        source=str(staged.get("source") or ""),
        source_url=str(staged.get("source_url") or ""),
        title=title,
        body=body,
        published_at=str(staged.get("published_at") or ""),
    )
    status = str(result.get("status") or "failed")
    normalized = {
        **staged,
        "item_id": item_id,
        "title": title,
        "body": body,
    }
    if status in {"succeeded", "reconciled"}:
        _finalize_editorial_publish(normalized, result)
        _remove_prepared(item_id)

    messages = {
        "succeeded": "نسخه‌ای که دیدی در تلگرام منتشر شد",
        "reconciled": "انتشار قبلی تأیید و همگام شد",
        "ambiguous": "وضعیت ارسال نامشخص است؛ انتشار دوباره مسدود شد",
        "processing": "انتشار در حال پردازش است",
        "failed": "انتشار ناموفق بود",
    }
    return _write_v4_result(
        command_id,
        "v3_publish_prepared",
        status,
        messages.get(status, "وضعیت انتشار ثبت شد"),
        item_id=item_id,
        story_id=str(result.get("story_id") or ""),
        telegram_message_id=result.get("telegram_message_id") if isinstance(result.get("telegram_message_id"), int) else None,
        error=str(result.get("error") or ""),
        final_title=title,
        final_body=body,
    )


def apply_command(path: str | Path) -> dict:
    command_path = Path(path)
    if not command_path.exists():
        existing = _read_json(_result_path(command_path.stem), None)
        if isinstance(existing, dict) and existing.get("status") in TERMINAL:
            return existing
        raise FileNotFoundError(command_path)

    payload = _command_payload(command_path)
    action = str(payload.get("action") or "")
    if action not in V4_ACTIONS:
        return apply_legacy_command(command_path)

    existing = _read_json(_result_path(str(payload["command_id"])), None)
    if isinstance(existing, dict) and existing.get("status") in TERMINAL:
        _consume(command_path)
        return existing

    command_id = str(payload["command_id"])
    item_id = str(payload.get("item_id") or "")
    _write_v4_result(command_id, action, "processing", "در حال پردازش", item_id=item_id)
    try:
        result = _apply_prepare(payload) if action == "v3_prepare" else _apply_publish_prepared(payload)
    except Exception as exc:
        result = _write_v4_result(
            command_id,
            action,
            "failed",
            "عملیات لونا ناموفق بود" if action == "v3_prepare" else "انتشار ناموفق بود",
            item_id=item_id,
            error=f"{type(exc).__name__}: {exc}",
        )
    _consume(command_path)
    return result
