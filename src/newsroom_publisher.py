from __future__ import annotations

import re
import tempfile
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL

from .formatters import format_news
from .newsroom_models import NormalizedNewsItem
from .services import USER_AGENT, translate_to_fa
from .sources import NewsItem


EXPLOSION_TERMS = ("explosion", "exploded", "blast", "detonation", "انفجار", "منفجر")
TELEGRAM_POST_RE = re.compile(r"^https?://t\.me/(?:s/)?[A-Za-z0-9_]+/\d+", re.I)


def _breaking_prefix(item: NormalizedNewsItem) -> str:
    text = f"{item.raw.title} {item.raw.summary}".lower()
    return "💥 🔴 <b>خبر فوری</b>\n" if any(term in text for term in EXPLOSION_TERMS) else ""


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


def _telegram_preview_url(url: str) -> str:
    clean = str(url or "").split("?", 1)[0]
    if "/s/" not in clean:
        clean = clean.replace("https://t.me/", "https://t.me/s/").replace("http://t.me/", "https://t.me/s/")
    return clean + "?single"


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
        return _breaking_prefix(item) + format_news(legacy, title_fa, summary_fa)

    def _telegram_post_has_video(self, url: str) -> bool:
        if not TELEGRAM_POST_RE.match(str(url or "")):
            return False
        try:
            response = self.session.get(_telegram_preview_url(url), headers={"User-Agent": USER_AGENT}, timeout=8)
            response.raise_for_status()
        except Exception:
            return False
        soup = BeautifulSoup(response.text, "html.parser")
        return bool(
            soup.select_one("video")
            or soup.select_one(".tgme_widget_message_video_player")
            or soup.select_one(".tgme_widget_message_video_thumb")
        )

    @staticmethod
    def _download_telegram_video(url: str, directory: str) -> Path | None:
        output = str(Path(directory) / "telegram-video.%(ext)s")
        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "best[ext=mp4]/best",
            "outtmpl": output,
            "socket_timeout": 20,
            "retries": 1,
        }
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([str(url).split("?", 1)[0]])
        except Exception:
            return None
        candidates = sorted(Path(directory).glob("telegram-video.*"), key=lambda p: p.stat().st_size, reverse=True)
        return candidates[0] if candidates and candidates[0].stat().st_size > 0 else None

    def _post(self, endpoint: str, *, data: dict, files=None, timeout: int = 35) -> dict:
        try:
            response = self.session.post(
                f"https://api.telegram.org/bot{self.bot_token}/{endpoint}",
                data=data,
                files=files,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
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

    def __call__(self, item: NormalizedNewsItem) -> dict:
        if not self.bot_token or not self.chat_id:
            return {"ok": False, "error": "missing_telegram_credentials"}
        message = self._message(item)
        if not message:
            return {"ok": False, "error": "translation_or_format_failed"}

        video = _first_video(item)
        photo = _first_image(item)
        if video:
            return self._post(
                "sendVideo",
                data={"chat_id": self.chat_id, "video": video, "caption": message[:1024], "parse_mode": "HTML", "supports_streaming": "true"},
                timeout=40,
            )

        # Public Telegram OSINT channels often expose the post but not a direct
        # mp4 URL in our feed model. Detect the video first, then download only
        # those posts and upload the actual file to Bikhabar.
        source_url = str(item.raw.source_url or "").strip()
        if self._telegram_post_has_video(source_url):
            with tempfile.TemporaryDirectory(prefix="bikhabar-video-") as directory:
                path = self._download_telegram_video(source_url, directory)
                if path is not None:
                    try:
                        with path.open("rb") as handle:
                            return self._post(
                                "sendVideo",
                                data={"chat_id": self.chat_id, "caption": message[:1024], "parse_mode": "HTML", "supports_streaming": "true"},
                                files={"video": (path.name, handle, "video/mp4")},
                                timeout=120,
                            )
                    except OSError:
                        pass

        if photo:
            return self._post(
                "sendPhoto",
                data={"chat_id": self.chat_id, "photo": photo, "caption": message[:1024], "parse_mode": "HTML"},
                timeout=30,
            )

        return self._post(
            "sendMessage",
            data={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=25,
        )
