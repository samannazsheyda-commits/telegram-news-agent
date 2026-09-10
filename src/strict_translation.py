from __future__ import annotations

from . import services
from .newsroom_publisher import TelegramNewsroomPublisher


def translate_to_fa_strict(text: str, session=None) -> str:
    """Translate auto-published newsroom copy using only Google paths.

    Automatic Telegram publication fails closed when both high-confidence
    paths fail. MyMemory and public Lingva instances are deliberately excluded
    from this path so weak fallback text cannot become final channel copy.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    if services.has_persian(raw):
        return services._polish_fa(raw)
    resolved_session = session or services.requests
    for translator in (services._google_translate, services._google_mobile_translate):
        try:
            translated = services._polish_fa(translator(raw, session=resolved_session))
            translated = services._repair_news_idioms(raw, translated)
            if services._translation_quality_ok(raw, translated):
                return translated
        except Exception as exc:
            print(
                f"STRICT_TRANSLATION_BACKEND_FAILED backend={translator.__name__} type={type(exc).__name__}",
                flush=True,
            )
    print("STRICT_TRANSLATION_FAILED", flush=True)
    return ""


class StrictTelegramNewsroomPublisher(TelegramNewsroomPublisher):
    """Production publisher that never falls through to Lingva."""

    def __init__(self, bot_token: str, chat_id: str, *, session=services.requests, translator=None):
        resolved = translator or (lambda text: translate_to_fa_strict(text, session=session))
        super().__init__(bot_token, chat_id, session=session, translator=resolved)

    def _translate_resilient(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        try:
            translated = str(self.translator(raw) or "").strip()
        except Exception as exc:
            print(f"STRICT_TRANSLATION_CALL_FAILED type={type(exc).__name__}", flush=True)
            return ""
        return translated if services.has_persian(translated) else ""
