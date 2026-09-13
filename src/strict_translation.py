from __future__ import annotations

import re

from . import services
from .persian_editor import edit_news_text
from .newsroom_publisher import TelegramNewsroomPublisher


_MECHANICAL_NEWS_PATTERNS = (
    re.compile(r"حملات?\s+هوایی.{0,180}?زده\s+(?:است|شد|شده)", re.I),
    re.compile(r"به\s+یک\s+نقطه\s+خفه[‌\s-]*کننده", re.I),
)

# Deterministic actor guard after the LLM editor. This deliberately covers the
# recurring actors in Bikhabar's Iran/regional beat; it is a last safety net,
# not a replacement for the model's source-aware faithful=true decision.
_ENTITY_PRESERVATION_RULES = (
    (("iran", "iranian"), ("ایران", "ایرانی")),
    (("israel", "israeli"), ("اسرائیل", "اسرائیلی")),
    (("saudi arabia", "saudi"), ("عربستان", "سعودی")),
    (("yemen", "yemeni"), ("یمن", "یمنی")),
    (("houthi", "houthis", "ansar allah"), ("حوثی", "انصارالله")),
    (("united states", "american", "u.s."), ("آمریکا", "آمریکایی")),
    (("oman", "omani"), ("عمان", "عمانی")),
    (("iraq", "iraqi"), ("عراق", "عراقی")),
    (("qatar", "qatari"), ("قطر", "قطری")),
    (("bahrain", "bahraini"), ("بحرین", "بحرینی")),
    (("uae", "united arab emirates", "emirati"), ("امارات", "اماراتی")),
    (("turkey", "turkish", "türkiye"), ("ترکیه", "ترک")),
    (("russia", "russian"), ("روسیه", "روسی")),
    (("china", "chinese"), ("چین", "چینی")),
    (("trump", "donald trump"), ("ترامپ",)),
    (("mohammed bin salman", "mohammad bin salman", "mbs"), ("محمد بن سلمان",)),
    (("centcom", "central command"), ("سنتکام", "فرماندهی مرکزی")),
    (("irgc", "revolutionary guard"), ("سپاه",)),
    (("hezbollah",), ("حزب‌الله", "حزب الله")),
    (("hamas",), ("حماس",)),
)


def translate_to_fa_strict(text: str, session=None) -> str:
    """Translate auto-published newsroom copy through guarded fallbacks.

    Google remains the preferred path. If both Google endpoints are unavailable,
    MyMemory is allowed only as a last-resort transport because its output must
    still pass the same semantic, numeric, idiom and Persian editorial gates
    before it can reach Telegram. Public Lingva instances remain excluded here.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    if services.has_persian(raw):
        return services._polish_fa(raw)
    resolved_session = session or services.requests
    for translator in (
        services._google_translate,
        services._google_mobile_translate,
        services._mymemory_translate,
    ):
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


def _preserves_key_entities(source: str, edited: str) -> bool:
    source_lower = str(source or "").lower()
    value = str(edited or "")
    for source_terms, persian_terms in _ENTITY_PRESERVATION_RULES:
        if any(term in source_lower for term in source_terms) and not any(term in value for term in persian_terms):
            return False
    return True


def _natural_persian_copy(source: str, value: str) -> str:
    edited = edit_news_text(source, value)
    if not edited:
        return ""
    if any(pattern.search(edited) for pattern in _MECHANICAL_NEWS_PATTERNS):
        return ""
    if not _preserves_key_entities(source, edited):
        return ""
    if not services.translation_is_publishable(source, edited):
        return ""
    return services._polish_fa(edited)


class StrictTelegramNewsroomPublisher(TelegramNewsroomPublisher):
    """Production publisher with optional/required AI translation and editing."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        session=services.requests,
        translator=None,
        ai=None,
        ai_mode: str = "optional",
    ):
        resolved = translator or (lambda text: translate_to_fa_strict(text, session=session))
        super().__init__(bot_token, chat_id, session=session, translator=resolved)
        mode = str(ai_mode or "optional").strip().lower()
        self.ai_mode = mode if mode in {"off", "optional", "required"} else "optional"
        self.ai = ai

    def _translate_with_ai(self, raw: str) -> str:
        if self.ai is None or not bool(getattr(self.ai, "available", True)):
            return ""
        try:
            draft = self.ai.translate_to_fa(raw)
            draft_text = str(getattr(draft, "text", "") or "").strip()
            if not draft_text or getattr(draft, "faithful", True) is not True:
                return ""
            edit = self.ai.edit_persian(raw, draft_text)
            if getattr(edit, "faithful", False) is not True or getattr(edit, "natural", False) is not True:
                return ""
            final_text = str(getattr(edit, "text", "") or "").strip()
            return _natural_persian_copy(raw, final_text)
        except Exception as exc:
            print(f"AI_TRANSLATION_EDITOR_FAILED type={type(exc).__name__} error={exc}", flush=True)
            return ""

    def _translate_resilient(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        if services.has_persian(raw):
            return services._polish_fa(raw)

        if self.ai_mode != "off":
            translated = self._translate_with_ai(raw)
            if translated:
                return translated
            if self.ai_mode == "required":
                print("AI_TRANSLATION_REQUIRED_REJECTED", flush=True)
                return ""

        try:
            translated = str(self.translator(raw) or "").strip()
        except Exception as exc:
            print(f"STRICT_TRANSLATION_CALL_FAILED type={type(exc).__name__}", flush=True)
            return ""
        if not translated:
            return ""
        translated = services._repair_news_idioms(raw, translated)
        return _natural_persian_copy(raw, translated)
