from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests

from .ai_newsroom import AIServiceError, HuggingFaceNewsAI
from .local_semantic_ai import LocalFirstNewsAI
from .openrouter_newsroom_ai import _decode_openrouter_content


_DEFAULT_BASE_URL = "https://1xai.ir/v1"
_DEFAULT_MODEL = "gpt-5.6-luna"
_ALLOWED_MODES = {"off", "optional", "required"}


@dataclass(frozen=True)
class OneXAIConfig:
    api_key: str = ""
    base_url: str = _DEFAULT_BASE_URL
    mode: str = "optional"
    model: str = _DEFAULT_MODEL
    event_memory_hours: int = 72
    duplicate_threshold: float = 0.87
    importance_threshold: int = 70
    timeout_seconds: int = 25
    request_min_interval_ms: int = 500
    request_max_retries: int = 4
    token: str = ""
    embedding_model: str = "local"
    editorial_model: str = _DEFAULT_MODEL
    persian_editor_model: str = _DEFAULT_MODEL
    translation_model: str = _DEFAULT_MODEL
    madlad_endpoint: str = ""

    @classmethod
    def from_env(cls) -> "OneXAIConfig":
        mode = str(os.environ.get("AI_NEWSROOM_MODE", "optional") or "optional").strip().lower()
        if mode not in _ALLOWED_MODES:
            mode = "optional"
        model = str(os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL) or _DEFAULT_MODEL).strip()
        base_url = str(os.environ.get("OPENAI_BASE_URL", _DEFAULT_BASE_URL) or _DEFAULT_BASE_URL).strip().rstrip("/")
        return cls(
            api_key=str(os.environ.get("OPENAI_API_KEY", "") or "").strip(),
            base_url=base_url,
            mode=mode,
            model=model,
            editorial_model=model,
            persian_editor_model=model,
            translation_model=model,
            event_memory_hours=_env_int("AI_EVENT_MEMORY_HOURS", 72, 1, 720),
            duplicate_threshold=_env_float("AI_DUPLICATE_THRESHOLD", 0.87, 0.0, 1.0),
            importance_threshold=_env_int("AI_IMPORTANCE_THRESHOLD", 70, 0, 100),
            timeout_seconds=_env_int("AI_NEWSROOM_TIMEOUT_SECONDS", 25, 5, 120),
            request_min_interval_ms=_env_int("AI_REQUEST_MIN_INTERVAL_MS", 500, 0, 5000),
            request_max_retries=_env_int("AI_REQUEST_MAX_RETRIES", 4, 0, 8),
        )


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _decode_one_x_ai_content(content: Any) -> dict[str, Any]:
    """Decode Luna JSON while tolerating harmless prose around exactly one object.

    The normal structured decoder remains the first path. Some 1xAI/Luna
    responses have nevertheless returned a short acknowledgement before or
    after an otherwise valid JSON object. For this provider only, recover one
    complete top-level object with ``JSONDecoder.raw_decode``. More than one
    valid object is ambiguous and therefore fails closed.
    """
    try:
        return _decode_openrouter_content(content)
    except AIServiceError as strict_error:
        if not isinstance(content, str):
            raise AIServiceError("invalid_1xai_json") from strict_error

    text = content.strip()
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    cursor = 0

    while cursor < len(text):
        start = text.find("{", cursor)
        if start < 0:
            break
        try:
            value, consumed = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        if isinstance(value, dict):
            if found is not None:
                raise AIServiceError("invalid_1xai_json_multiple_objects")
            found = value
            cursor = start + consumed
            continue
        cursor = start + max(1, consumed)

    if found is None:
        raise AIServiceError("invalid_1xai_json")
    return found


class OneXAINewsAI(HuggingFaceNewsAI):
    """1xAI/OpenAI-compatible provider using the shared newsroom contracts."""

    def __init__(self, config: OneXAIConfig | None = None, *, session=requests):
        super().__init__(config or OneXAIConfig.from_env(), session=session)

    @property
    def available(self) -> bool:
        return bool(self.config.api_key) and self.config.mode != "off"

    def _headers(self) -> dict[str, str]:
        if not self.config.api_key:
            raise AIServiceError("missing_1xai_api_key")
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "BikhabarNewsroom/3.0",
        }

    def _post_json(self, url: str, payload: dict[str, Any], *, timeout: int | None = None) -> Any:
        try:
            return super()._post_json(url, payload, timeout=timeout)
        except AIServiceError as exc:
            message = str(exc)
            if message.startswith("hf_"):
                raise AIServiceError("1xai_" + message[3:]) from exc
            raise

    def _chat_json(self, *, model: str, system: str, user: str, max_tokens: int = 500) -> dict[str, Any]:
        endpoint = f"{self.config.base_url.rstrip('/')}/chat/completions"
        current_system = system
        current_max_tokens = max_tokens

        for attempt in range(2):
            payload = self._post_json(
                endpoint,
                {
                    "model": model or self.config.model,
                    "messages": [
                        {"role": "system", "content": current_system},
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": current_max_tokens,
                    "response_format": {"type": "json_object"},
                },
            )
            try:
                content = payload["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise AIServiceError("invalid_1xai_chat_response") from exc

            try:
                return _decode_one_x_ai_content(content)
            except AIServiceError:
                if attempt >= 1:
                    raise
                current_system = (
                    system
                    + "\nCRITICAL RETRY: Return exactly one JSON object and nothing else. "
                    + "No prose, no markdown fences, no acknowledgement."
                )
                current_max_tokens = max(320, max_tokens * 2)

        raise AIServiceError("invalid_1xai_json")

    def _chat_text(self, *, model: str, system: str, user: str, max_tokens: int = 500) -> str:
        endpoint = f"{self.config.base_url.rstrip('/')}/chat/completions"
        payload = self._post_json(
            endpoint,
            {
                "model": model or self.config.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
            },
        )
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("invalid_1xai_chat_response") from exc
        if not isinstance(content, str):
            raise AIServiceError("invalid_1xai_chat_response")
        return content.strip()


class LocalFirstOneXAINewsAI(LocalFirstNewsAI, OneXAINewsAI):
    """Local duplicate shortlisting plus 1xAI Luna language decisions."""

    pass
