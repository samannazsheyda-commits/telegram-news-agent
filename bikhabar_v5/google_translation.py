from __future__ import annotations

from typing import Any

import requests


class GoogleTranslateClient:
    endpoint = "https://translate.googleapis.com/translate_a/single"

    def __init__(self, *, session: Any | None = None, timeout_seconds: float = 12) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    def _translate_text(self, text: str, *, target_language: str) -> str:
        if not text:
            return ""
        response = self.session.get(
            self.endpoint,
            params={
                "client": "gtx",
                "sl": "auto",
                "tl": target_language,
                "dt": "t",
                "q": text,
            },
            timeout=self.timeout_seconds,
            headers={"User-Agent": "Bikhabar-Vision5/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        try:
            segments = payload[0]
            translated = "".join(str(segment[0]) for segment in segments if segment[0])
        except (IndexError, KeyError, TypeError) as exc:
            raise RuntimeError("Google returned a malformed translation payload") from exc
        if not translated.strip():
            raise RuntimeError("Google returned a malformed translation payload")
        return translated.strip()

    def translate(self, *, title: str, body: str, target_language: str) -> dict[str, str]:
        language = str(target_language or "").strip()
        if not language:
            raise ValueError("target_language is required")
        return {
            "title": self._translate_text(str(title or "").strip(), target_language=language),
            "body": self._translate_text(str(body or "").strip(), target_language=language),
        }
