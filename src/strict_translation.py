from __future__ import annotations

from . import services


def translate_to_fa_strict(text: str, session=None) -> str:
    """Translate newsroom copy using only the two Google paths.

    Automatic Telegram publication must fail closed when both high-confidence
    paths fail. MyMemory/Lingva remain outside this path so weak fallback text
    cannot be sent to the channel as final copy.
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
