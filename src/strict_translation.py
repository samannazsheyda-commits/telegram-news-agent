from __future__ import annotations

import re

from . import newsroom_publisher as newsroom_publisher_module
from . import services
from .offline_translation import translate_to_fa_offline
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
    """Translate auto-published newsroom copy through guarded network fallbacks."""
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


def _repair_irgc_navy_actor(source: str, translated: str) -> str:
    """Restore IRGC Navy only when the English source explicitly names it.

    The compact offline translator can collapse "Iran's IRGC Navy" into the
    materially different generic actor "نیروی دریایی ایران". That must not be
    published as-is, but the source gives enough information to repair the actor
    deterministically without inventing a fact.
    """
    source_lower = str(source or "").lower()
    value = services._polish_fa(str(translated or ""))
    if not any(
        phrase in source_lower
        for phrase in (
            "irgc navy",
            "revolutionary guard navy",
            "islamic revolutionary guard corps navy",
        )
    ):
        return value
    if "سپاه" in value:
        return value

    for generic_actor in (
        "نیروی دریایی جمهوری اسلامی ایران",
        "نیروی دریایی ایران",
    ):
        if generic_actor in value:
            return services._polish_fa(
                value.replace(
                    generic_actor,
                    "نیروی دریایی سپاه پاسداران انقلاب اسلامی ایران",
                    1,
                )
            )
    return value


def _repair_struck_casualty_role_reversal(source: str, translated: str) -> str:
    """Repair one observed Argos role reversal only when the English source anchors it.

    Argos can mistranslate "vessel was struck, killing ..." as if the vessel
    itself were killed and then killed/wounded people. The rewrite is allowed
    only when the source explicitly says the subject was struck and separately
    describes casualties, so ordinary Persian uses of "به قتل رسید" are untouched.
    """
    source_lower = str(source or "").lower()
    value = services._polish_fa(str(translated or ""))
    if "struck" not in source_lower:
        return value
    if not any(term in source_lower for term in ("killing", "killed", "wounding", "wounded", "leaving")):
        return value

    match = re.match(
        r"^(?P<victim>.+?)\s+به قتل رسید\s+و\s+"
        r"(?P<killed>[^،؛.!؟]+?نفر)\s+را کشت\s+و\s+"
        r"(?P<wounded>[^،؛.!؟]+?نفر(?:\s+دیگر)?)\s+را زخمی کرد[.!؟]?$",
        value,
    )
    if not match:
        return value
    return services._polish_fa(
        f"{match.group('victim')} هدف قرار گرفت؛ "
        f"{match.group('killed')} کشته و {match.group('wounded')} زخمی شدند."
    )


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
    """Production publisher with guarded network/AI translation and opt-in local MT."""

    send_still_photos = False

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        session=services.requests,
        translator=None,
        offline_translator=None,
        offline_translation_enabled: bool = False,
        ai=None,
        ai_mode: str = "optional",
    ):
        resolved = translator or (lambda text: translate_to_fa_strict(text, session=session))
        super().__init__(bot_token, chat_id, session=session, translator=resolved)
        mode = str(ai_mode or "optional").strip().lower()
        self.ai_mode = mode if mode in {"off", "optional", "required"} else "optional"
        self.ai = ai
        self.offline_translator = offline_translator or translate_to_fa_offline
        self.offline_translation_enabled = bool(offline_translation_enabled)

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

    def _guard_translation(self, raw: str, translated: str) -> str:
        value = str(translated or "").strip()
        if not value:
            return ""
        value = _repair_irgc_navy_actor(raw, value)
        value = _repair_struck_casualty_role_reversal(raw, value)
        value = services._repair_news_idioms(raw, value)
        return _natural_persian_copy(raw, value)

    def _translate_resilient(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        if services.has_persian(raw):
            return services._polish_fa(raw)

        # The compact Argos model remains available for explicit/manual use, but
        # it is not allowed on the default synchronous production path. On the
        # 1-CPU/low-memory VPS a local inference can block the whole newsroom.
        if self.offline_translation_enabled and self.ai_mode != "required":
            try:
                offline = str(self.offline_translator(raw) or "").strip()
            except Exception as exc:
                print(f"OFFLINE_TRANSLATION_CALL_FAILED type={type(exc).__name__}", flush=True)
                offline = ""
            guarded = self._guard_translation(raw, offline)
            if guarded:
                return guarded

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
            translated = ""

        guarded = self._guard_translation(raw, translated)
        if guarded:
            return guarded

        fallback = newsroom_publisher_module._lingva_translate(raw, session=self.session)
        guarded = self._guard_translation(raw, fallback)
        if guarded:
            print("STRICT_TRANSLATION_LINGVA_FALLBACK_OK", flush=True)
            return guarded

        print("STRICT_TRANSLATION_ALL_FALLBACKS_FAILED", flush=True)
        return ""

    def _message(self, item):
        """Build safe Persian output, allowing headline-only degradation in optional mode.

        The title must always pass the full translation/editorial guard. When the
        source also supplied a summary but every summary backend is unavailable or
        rejected, optional mode may omit only that supplemental summary instead of
        dropping the already-vetted headline. Required AI mode remains fail-closed.
        """
        title_fa = self._translate_resilient(item.raw.title)
        if not title_fa:
            return ""

        summary_fa = self._translate_resilient(item.raw.summary) if item.raw.summary else ""
        if item.raw.summary and not summary_fa:
            if self.ai_mode == "required":
                return ""
            print(
                f"SUMMARY_TRANSLATION_SKIPPED_HEADLINE_ONLY source={item.raw.source!r}",
                flush=True,
            )

        legacy = newsroom_publisher_module.NewsItem(
            key=item.raw.source_item_id,
            source=item.raw.source,
            title=item.raw.title,
            summary=item.raw.summary,
            link=item.raw.source_url,
            published=newsroom_publisher_module._published_rfc2822(item.raw.published_at),
        )
        message = newsroom_publisher_module.format_news(legacy, title_fa, summary_fa)
        if not message:
            return ""
        if newsroom_publisher_module._is_explosion(item):
            message = newsroom_publisher_module._collapse_breaking_header(message)
        return newsroom_publisher_module.finalize_telegram_message(message)
