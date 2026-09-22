from __future__ import annotations

from typing import Any

import requests


class TelegramAPIError(RuntimeError):
    pass


class TelegramBotClient:
    def __init__(
        self,
        *,
        token: str,
        chat_id: str,
        session: Any | None = None,
        timeout_seconds: float = 20,
    ) -> None:
        self.token = str(token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        if not self.token or not self.chat_id:
            raise ValueError("Telegram token and chat_id are required")
        self.session = session or requests.Session()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.api_root = f"https://api.telegram.org/bot{self.token}"

    def send(self, *, text: str, media: dict[str, Any] | None = None) -> dict[str, int]:
        copy = str(text or "").strip()
        if not copy:
            raise ValueError("Telegram message text is required")
        media = dict(media or {})
        media_type = str(media.get("type") or "").strip().lower()
        media_url = str(media.get("url") or "").strip()
        if media_type in {"photo", "video", "document"} and media_url and len(copy) > 1024:
            raise ValueError("Telegram media caption exceeds 1024 characters")
        if not media_url and len(copy) > 4096:
            raise ValueError("Telegram text message exceeds 4096 characters")
        if media_type == "photo" and media_url:
            method = "sendPhoto"
            data = {"chat_id": self.chat_id, "photo": media_url, "caption": copy}
        elif media_type == "video" and media_url:
            method = "sendVideo"
            data = {"chat_id": self.chat_id, "video": media_url, "caption": copy}
        elif media_type == "document" and media_url:
            method = "sendDocument"
            data = {"chat_id": self.chat_id, "document": media_url, "caption": copy}
        else:
            method = "sendMessage"
            data = {"chat_id": self.chat_id, "text": copy, "disable_web_page_preview": "false"}
        response = self.session.post(
            f"{self.api_root}/{method}",
            data=data,
            timeout=self.timeout_seconds,
        )
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise TelegramAPIError("Telegram returned a malformed response") from exc
        if response.status_code >= 400 or not payload.get("ok"):
            description = str(payload.get("description") or f"HTTP {response.status_code}")
            raise TelegramAPIError(f"Telegram rejected the message: {description}")
        try:
            message_id = int(payload["result"]["message_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TelegramAPIError("Telegram response did not contain message_id") from exc
        return {"message_id": message_id}
