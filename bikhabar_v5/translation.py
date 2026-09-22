from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class TranslationError(RuntimeError):
    pass


def is_usable_persian(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return False
    persian = sum(1 for char in letters if "\u0600" <= char <= "\u06ff")
    return persian / len(letters) >= 0.55


def _validated_copy(payload: Mapping[str, Any], *, provider: str) -> dict[str, str]:
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not is_usable_persian(title) or (body and not is_usable_persian(body)):
        raise TranslationError(f"{provider} did not return usable Persian copy")
    return {"provider": provider, "title": title, "body": body}


class TranslationPipeline:
    def __init__(self, *, google: Any, luna: Any | None = None, max_attempts: int = 3) -> None:
        self.google = google
        self.luna = luna
        self.max_attempts = max(1, min(int(max_attempts), 5))

    def translate_google(self, story: Mapping[str, Any]) -> dict[str, str]:
        title = str(story.get("original_title") or "").strip()
        body = str(story.get("original_text") or "").strip()
        if is_usable_persian(title) and (not body or is_usable_persian(body)):
            return {"provider": "source_persian", "title": title, "body": body}

        last_error: Exception | None = None
        for _attempt in range(self.max_attempts):
            try:
                response = self.google.translate(title=title, body=body, target_language="fa")
                return _validated_copy(response, provider="google")
            except TranslationError:
                raise
            except Exception as exc:
                last_error = exc
        detail = str(last_error or "provider unavailable")
        raise TranslationError(f"Google translation failed: {detail}") from last_error

    def translate_luna(self, story: Mapping[str, Any]) -> dict[str, str]:
        if self.luna is None:
            raise TranslationError("Luna translation is not configured")
        title = str(story.get("original_title") or "").strip()
        body = str(story.get("original_text") or "").strip()
        try:
            response = self.luna.translate(title=title, body=body, target_language="fa")
        except Exception as exc:
            raise TranslationError(f"Luna translation failed: {exc}") from exc
        return _validated_copy(response, provider="luna")


def select_final_copy(story: Mapping[str, Any], mode: str) -> tuple[str, str]:
    normalized = str(mode or "").strip().lower()
    if normalized == "google":
        title = str(story.get("google_title") or "").strip()
        body = str(story.get("google_body") or "").strip()
    elif normalized == "luna":
        title = str(story.get("luna_title") or "").strip()
        body = str(story.get("luna_body") or "").strip()
    else:
        raise TranslationError(f"unsupported final copy mode: {mode}")
    if not title:
        raise TranslationError(f"{normalized} copy is not ready")
    return title, body
