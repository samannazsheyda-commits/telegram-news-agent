from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime

import requests

from .formatters import format_news
from .newsroom_models import NormalizedNewsItem
from .services import USER_AGENT, translate_to_fa
from .sources import NewsItem


def _published_rfc2822(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return format_datetime(dt.astimezone(timezone.utc))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return format_datetime(dt.astimezone(timezone.utc))
    except Exception:
        return ""


def _first_media(item: NormalizedNewsItem, kinds: set[str]) -> str:
    for media in item.raw.media or []:
        if not isinstance(media, dict):
            continue
        kind = str(media.get("type") or "").lower().strip()
        url = str(media.get("url") or media.get("preview_url") or "").strip()
        if url and kind in kinds:
            return url
    return ""


def _first_image(item: NormalizedNewsItem) -> str:
    return _first_media(item, {"image", "photo"})


def _first_video(item: NormalizedNewsItem) -> str:
    return _first_media(item, {"video", "mp4", "gif"})


class TelegramNewsroomPublisher:
    def __init__(self, bot_token: str, chat_id: str, *, session=requests, translator=translate_to_fa):
        self.bot_token = str(bot_token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.session = session
        self.translator = translator

    def _message(self, item: NormalizedNewsItem) -> str:
        title_fa = str(self.translator(item.raw.title) or "").strip()
        if not title_fa:
            return ""
        summary_fa = str(self.translator(item.raw.summary) or "").strip() if item.raw.summary else ""
        legacy = NewsItem(
            key=item.raw.source_item_id,
            source=item.raw.source,
            title=item.raw.title,
            summary=item.raw.summary,
            link=item.raw.source_url,
            published=_published_rfc2822(item.raw.published_at),
        )
        return format_news(legacy, title_fa, summary_fa)

    def __call__(self, item: NormalizedNewsItem) -> dict:
        if not self.bot_token or not self.chat_id:
            return {"ok": False, "error": "missing_telegram_credentials"}

        message = self._message(item)
        if not message:
            return {"ok": False, "error": "translation_or_format_failed"}

        video = _first_video(item)
        photo = _first_image(item)
        if video:
            endpoint = "sendVideo"
            data = {
                "chat_id": self.chat_id,
                "video": video,
                "caption": message[:1024],
                "parse_mode": "HTML",
                "supports_streaming": "true",
            }
        elif photo:
            endpoint = "sendPhoto"
            data = {
                "chat_id": self.chat_id,
                "photo": photo,
                "caption": message[:1024],
                "parse_mode": "HTML",
            }
        else:
            endpoint = "sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }

        try:
            response = self.session.post(
                f"https://api.telegram.org/bot{self.bot_token}/{endpoint}",
                data=data,
                headers={"User-Agent": USER_AGENT},
                timeout=35 if video else 25,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return {"ok": False, "error": f"telegram_request_failed:{type(exc).__name__}"}

        result = payload.get("result") if isinstance(payload, dict) else None
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if not isinstance(payload, dict) or payload.get("ok") is not True or not isinstance(message_id, int):
            description = str(payload.get("description") or "telegram_unverified_response") if isinstance(payload, dict) else "telegram_unverified_response"
            return {"ok": False, "error": description}
        return {"ok": True, "message_id": message_id}
