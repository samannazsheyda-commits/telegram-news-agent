from __future__ import annotations

from typing import Any, Iterable, Mapping

from .common import finalize_candidate, source_fields


def collect_telegram_messages(
    messages: Iterable[Mapping[str, Any]], source: Mapping[str, Any]
) -> list[dict[str, Any]]:
    source_id, display_name = source_fields(source)
    rows: list[dict[str, Any]] = []
    for message in messages:
        message_id = str(message.get("message_id") or "").strip()
        text = str(message.get("text") or message.get("caption") or "").strip()
        chat = message.get("chat") if isinstance(message.get("chat"), Mapping) else {}
        username = str(chat.get("username") or source.get("identity") or "").strip().lstrip("@")
        if not message_id or not text or not username:
            continue
        media_value = message.get("media")
        media = [dict(media_value)] if isinstance(media_value, Mapping) and media_value.get("url") else []
        rows.append(
            finalize_candidate(
                {
                    "source_id": source_id,
                    "source": display_name,
                    "source_url": f"https://t.me/{username}/{message_id}",
                    "original_title": text.splitlines()[0][:280],
                    "original_text": text,
                    "published_at_source": str(message.get("date") or ""),
                    "media_json": {"items": media},
                }
            )
        )
    return rows
