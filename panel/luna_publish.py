from __future__ import annotations

import re
from typing import Callable


_FA_RE = re.compile(r"[\u0600-\u06ff]")


def publish_tool_schema() -> dict:
    return {
        "type": "function",
        "name": "publish_story",
        "description": "انتشار یک خبر مشخص با همان نسخه فارسی قابل مشاهده در پنل. قبل از انتشار حتماً تأیید کاربر گرفته می‌شود.",
        "parameters": {
            "type": "object",
            "properties": {"story_id": {"type": "string"}},
            "required": ["story_id"],
            "additionalProperties": False,
        },
    }


def _story_id(row: dict) -> str:
    return str(row.get("id") or row.get("item_id") or row.get("story_id") or "").strip()


def _find_live_story(data, story_id: str) -> dict | None:
    value, _ = data.read_json("data/panel_live_feed.json", [])
    for row in value if isinstance(value, list) else []:
        if isinstance(row, dict) and _story_id(row) == story_id:
            return dict(row)
    return None


def _visible_persian_copy(row: dict) -> tuple[str, str]:
    final_ready = str(row.get("luna_translation_status") or "") == "passed"
    if final_ready:
        title = str(row.get("final_persian_title") or "").strip()
        body = str(row.get("final_persian_body") or "").strip()
        if title and _FA_RE.search(title):
            return title, body
    title = str(row.get("persian_title") or "").strip()
    body = str(row.get("persian_body") or "").strip()
    return title, body


def publish_story(
    data,
    story_id: str,
    *,
    enqueue: Callable[..., str],
    confirmed: bool = False,
) -> dict:
    story_id = str(story_id or "").strip()
    if not story_id:
        return {"ok": False, "error": "story_id_required", "message": "شناسه خبر لازم است."}

    row = _find_live_story(data, story_id)
    if row is None:
        return {"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد."}

    title, body = _visible_persian_copy(row)
    if not title or not _FA_RE.search(title):
        return {
            "ok": False,
            "error": "persian_copy_not_ready",
            "message": "ترجمه فارسی این خبر هنوز آماده انتشار نیست.",
        }

    source = str(row.get("source") or "").strip()
    source_url = str(row.get("source_url") or row.get("link") or "").strip()
    original_title = str(row.get("original_title") or row.get("title") or "").strip()
    original_body = str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip()
    if not source or not source_url or not original_title:
        return {
            "ok": False,
            "error": "publish_fields_missing",
            "message": "اطلاعات لازم برای انتشار کامل نیست.",
        }

    if not confirmed:
        return {
            "ok": True,
            "confirmation_required": True,
            "pending_action": {
                "action": "publish_story",
                "payload": {"story_id": story_id},
                "summary_fa": f"همین نسخه منتشر شود؟ «{title}»",
            },
        }

    command_id = enqueue(
        "v3_publish",
        item_id=story_id,
        news_key=str(row.get("news_key") or story_id),
        source=source,
        source_url=source_url,
        original_title=original_title,
        original_body=original_body,
        title=title,
        body=body,
        luna_v41_final=True,
        human_approved=True,
        published_at=str(row.get("published_at_source") or row.get("published") or ""),
    )
    return {
        "ok": True,
        "status": "queued",
        "command_id": command_id,
        "title": title,
        "message": "همان نسخه فارسی تأییدشده در صف امن انتشار قرار گرفت.",
    }
