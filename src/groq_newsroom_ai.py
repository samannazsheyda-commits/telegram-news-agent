from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from .ai_newsroom import AIServiceError, HuggingFaceNewsAI
from .local_semantic_ai import LocalFirstNewsAI


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_GROQ_MODEL = "qwen/qwen3.6-27b"
_ALLOWED_MODES = {"off", "optional", "required"}


@dataclass(frozen=True)
class GroqConfig:
    api_key: str = ""
    mode: str = "optional"
    model: str = _DEFAULT_GROQ_MODEL
    event_memory_hours: int = 72
    duplicate_threshold: float = 0.87
    importance_threshold: int = 70
    timeout_seconds: int = 25
    request_min_interval_ms: int = 500
    request_max_retries: int = 4
    # Compatibility fields consumed by the shared newsroom prompt/contract code.
    token: str = ""
    embedding_model: str = "local"
    editorial_model: str = _DEFAULT_GROQ_MODEL
    persian_editor_model: str = _DEFAULT_GROQ_MODEL
    translation_model: str = _DEFAULT_GROQ_MODEL
    madlad_endpoint: str = ""

    @classmethod
    def from_env(cls) -> "GroqConfig":
        mode = str(os.environ.get("AI_NEWSROOM_MODE", "optional") or "optional").strip().lower()
        if mode not in _ALLOWED_MODES:
            mode = "optional"
        model = str(os.environ.get("GROQ_MODEL", _DEFAULT_GROQ_MODEL) or _DEFAULT_GROQ_MODEL).strip()
        return cls(
            api_key=str(os.environ.get("GROQ_API_KEY", "") or "").strip(),
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


class GroqNewsAI(HuggingFaceNewsAI):
    """Groq-hosted Qwen provider using the existing strict newsroom contracts."""

    def __init__(self, config: GroqConfig | None = None, *, session=requests):
        super().__init__(config or GroqConfig.from_env(), session=session)

    @property
    def available(self) -> bool:
        return bool(self.config.api_key) and self.config.mode != "off"

    def _headers(self) -> dict[str, str]:
        if not self.config.api_key:
            raise AIServiceError("missing_groq_api_key")
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "BikhabarNewsroom/2.0",
        }

    def _post_json(self, url: str, payload: dict[str, Any], *, timeout: int | None = None) -> Any:
        try:
            return super()._post_json(url, payload, timeout=timeout)
        except AIServiceError as exc:
            message = str(exc)
            if message.startswith("hf_"):
                raise AIServiceError("groq_" + message[3:]) from exc
            raise

    def _chat_json(self, *, model: str, system: str, user: str, max_tokens: int = 500) -> dict[str, Any]:
        payload = self._post_json(
            GROQ_CHAT_URL,
            {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "reasoning_format": "hidden",
            },
        )
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("invalid_groq_chat_response") from exc
        from .ai_newsroom import _clean_json_content
        return _clean_json_content(content)


class LocalFirstGroqNewsAI(LocalFirstNewsAI, GroqNewsAI):
    """Local duplicate shortlisting plus Groq Qwen editorial/language decisions."""

    pass
