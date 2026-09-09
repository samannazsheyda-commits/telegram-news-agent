from __future__ import annotations

import re
import tempfile
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL

from .formatters import format_news
from .newsroom_models import NormalizedNewsItem
from .services import USER_AGENT, has_persian, translate_to_fa
from .sources import NewsItem


EXPLOSION_TERMS = ("explosion", "exploded", "blast", "detonation", "انفجار", "منفجر")
TELEGRAM_POST_RE = re.compile(r"^https?://t\.me/(?:s/)?[A-Za-z0-9_]+/\d+", re.I)
LINGVA_INSTANCES = (
    "https://lingva.ml",
    "https://translate.plausibility.cloud",
    "https://lingva.lunar.icu",
    "https://translate.projectsegfau.lt",
)


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


def _plain_text(html_text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", str(html_text or ""), flags=re.I)
    text = re.sub(r"</?(?:b|i|u|s|code|pre|a)(?:\s+[^>]*)?>", "", text, flags=re.I)
    return unescape(text).strip()


def _lingva_translate(text: str, session=requests) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    encoded = quote(raw, safe="")
    for base in LINGVA_INSTANCES:
        try:
            response = session.get(
                f"{base}/api/v1/en/fa/{encoded}",
                headers={"User-Agent": USER_AGENT},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
            translated = str(payload.get("translation") or "").strip() if isinstance(payload, dict) else ""
            if translated and has_persian(translated):
                print(f"TRANSLATION_LINGVA_OK instance={base}", flush=True)
                return translated
        except Exception as exc:
            print(f"TRANSLATION_LINGVA_FAILED instance={base} type={type(exc).__name__}", flush=True)
    return ""


class TelegramNewsroomPublisher:
    def __init__(self, bot_token: str, chat_id: str, *, session=requests, translator=translate_to_fa):
        self.bot_token = str(bot_token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.session = session
        self.translator = translator

    def _translate_resilient(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        translated = str(self.translator(raw) or "").strip()
        if translated:
            return translated
        return _lingva_translate(raw, session=self.session)

    def _message(self, item: NormalizedNewsItem) -> str:
        title_fa = self._translate_resilient(item.raw.title)
        if not title_fa:
            return ""
        summary_fa = self._translate_resilient(item.raw.summary) if item.raw.summary else ""
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

    def _raw_post(self, endpoint: str, *, data: dict, files=None, timeout: int = 35) -> dict:
        response = None
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
            detail = f"telegram_request_failed:{type(exc).__name__}"
            if response is not None:
                try:
                    payload = response.json()
                    description = str(payload.get("description") or "") if isinstance(payload, dict) else ""
                except Exception:
                    description = str(getattr(response, "text", "") or "")[:300]
                if description:
                    detail = f"{detail}:{description}"
            return {"ok": False, "error": detail}
        result = payload.get("result") if isinstance(payload, dict) else None
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if not isinstance(payload, dict) or payload.get("ok") is not True or not isinstance(message_id, int):
            description = str(payload.get("description") or "telegram_unverified_response") if isinstance(payload, dict) else "telegram_unverified_response"
            return {"ok": False, "error": description}
        return {"ok": True, "message_id": message_id}

    def _post(self, endpoint: str, *, data: dict, files=None, timeout: int = 35) -> dict:
        result = self._raw_post(endpoint, data=data, files=files, timeout=timeout)
        if result.get("ok") is True:
            return result
        error = str(result.get("error") or "")
        if endpoint == "sendMessage" and "parse" in error.lower() and data.get("text"):
            retry = dict(data)
            retry.pop("parse_mode", None)
            retry["text"] = _plain_text(str(data.get("text") or ""))
            result = self._raw_post(endpoint, data=retry, files=files, timeout=timeout)
            if result.get("ok") is True:
                return result
            error = str(result.get("error") or error)
        print(f"TELEGRAM_PUBLISH_FAILED endpoint={endpoint} error={error!r}", flush=True)
        return result

    def _text_post(self, message: str) -> dict:
        return self._post(
            "sendMessage",
            data={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=25,
        )

    def _fallback_to_text(self, message: str, failed_endpoint: str, result: dict) -> dict:
        print(
            f"TELEGRAM_MEDIA_FALLBACK_TO_TEXT endpoint={failed_endpoint} error={str(result.get('error') or '')!r}",
            flush=True,
        )
        return self._text_post(message)

    def __call__(self, item: NormalizedNewsItem) -> dict:
        if not self.bot_token or not self.chat_id:
            print("TELEGRAM_PUBLISH_FAILED endpoint=none error='missing_telegram_credentials'", flush=True)
            return {"ok": False, "error": "missing_telegram_credentials"}
        message = self._message(item)
        if not message:
            print(f"TELEGRAM_PUBLISH_FAILED endpoint=none error='translation_or_format_failed' source={item.raw.source!r}", flush=True)
            return {"ok": False, "error": "translation_or_format_failed"}

        video = _first_video(item)
        photo = _first_image(item)
        if video:
            result = self._post(
                "sendVideo",
                data={"chat_id": self.chat_id, "video": video, "caption": message[:1024], "parse_mode": "HTML", "supports_streaming": "true"},
                timeout=40,
            )
            if result.get("ok") is True:
                return result
            return self._fallback_to_text(message, "sendVideo", result)

        source_url = str(item.raw.source_url or "").strip()
        if self._telegram_post_has_video(source_url):
            with tempfile.TemporaryDirectory(prefix="bikhabar-video-") as directory:
                path = self._download_telegram_video(source_url, directory)
                if path is not None:
                    try:
                        with path.open("rb") as handle:
                            result = self._post(
                                "sendVideo",
                                data={"chat_id": self.chat_id, "caption": message[:1024], "parse_mode": "HTML", "supports_streaming": "true"},
                                files={"video": (path.name, handle, "video/mp4")},
                                timeout=120,
                            )
                        if result.get("ok") is True:
                            return result
                        return self._fallback_to_text(message, "sendVideo", result)
                    except OSError:
                        pass

        if photo:
            result = self._post(
                "sendPhoto",
                data={"chat_id": self.chat_id, "photo": photo, "caption": message[:1024], "parse_mode": "HTML"},
                timeout=30,
            )
            if result.get("ok") is True:
                return result
            return self._fallback_to_text(message, "sendPhoto", result)

        return self._text_post(message)
