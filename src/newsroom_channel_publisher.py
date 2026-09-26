from __future__ import annotations

import os

from .ai_newsroom import AIConfig, AIServiceError
from .groq_newsroom_ai import GroqConfig, LocalFirstGroqNewsAI
from .local_semantic_ai import LocalFirstNewsAI
from .one_x_ai_newsroom import OneXAIConfig, LocalFirstOneXAINewsAI
from .openrouter_newsroom_ai import OpenRouterConfig, LocalFirstOpenRouterNewsAI
from .strict_translation import StrictTelegramNewsroomPublisher


class _ProviderFailoverNewsAI:
    """Keep channel translation/editing alive when a configured remote AI provider fails.

    Providers are tried in priority order. Once a later provider succeeds, it
    becomes sticky for the rest of the process so a quota-exhausted provider is
    not retried immediately during the matching Persian edit call.
    """

    def __init__(self, providers: list[tuple[str, object]]):
        self._providers = list(providers)
        self._active_index = 0

    @property
    def available(self) -> bool:
        return any(
            bool(getattr(provider, "available", True))
            for _, provider in self._providers[self._active_index :]
        )

    def _call(self, method: str, *args):
        last_error: AIServiceError | None = None
        for index in range(self._active_index, len(self._providers)):
            name, provider = self._providers[index]
            if not bool(getattr(provider, "available", True)):
                self._active_index = index + 1
                continue
            try:
                result = getattr(provider, method)(*args)
            except AIServiceError as exc:
                last_error = exc
                self._active_index = index + 1
                print(
                    f"AI_PROVIDER_FAILOVER method={method} provider={name} error={exc}",
                    flush=True,
                )
                continue
            self._active_index = index
            return result

        if last_error is not None:
            raise last_error
        raise AIServiceError("no_ai_provider_available")

    def translate_to_fa(self, source_text: str):
        return self._call("translate_to_fa", source_text)

    def edit_persian(self, source_text: str, draft_text: str):
        return self._call("edit_persian", source_text, draft_text)


def _offline_translation_enabled() -> bool:
    raw = str(os.environ.get("OFFLINE_TRANSLATION_ENABLED", "0") or "0").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def build_channel_ai():
    """Assemble Luna-first remote AI for copy that will be sent to Telegram."""
    one_x_config = OneXAIConfig.from_env()
    hf_config = AIConfig.from_env()
    groq_config = GroqConfig.from_env()
    openrouter_config = OpenRouterConfig.from_env()

    providers: list[tuple[str, object]] = []
    if one_x_config.mode != "off" and one_x_config.api_key:
        providers.append(("1xai", LocalFirstOneXAINewsAI(one_x_config)))
    if openrouter_config.mode != "off" and openrouter_config.api_key:
        providers.append(("openrouter", LocalFirstOpenRouterNewsAI(openrouter_config)))
    if groq_config.mode != "off" and groq_config.api_key:
        providers.append(("groq", LocalFirstGroqNewsAI(groq_config)))
    if hf_config.mode != "off" and hf_config.token:
        providers.append(("huggingface", LocalFirstNewsAI(hf_config)))
    return _ProviderFailoverNewsAI(providers) if providers else None


def build_channel_copy_publisher() -> StrictTelegramNewsroomPublisher:
    """Build the publisher used for messages that go directly to the channel.

    Luna/1xAI is the editor and translator on this path. Free Google/Lingva
    fallbacks are never used: if Luna (and any configured AI failover) cannot
    produce guarded Persian copy, the send is fail-closed.
    """
    return StrictTelegramNewsroomPublisher(
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID", "@bikhabaar"),
        ai=build_channel_ai(),
        ai_mode="required",
        offline_translation_enabled=_offline_translation_enabled(),
    )
