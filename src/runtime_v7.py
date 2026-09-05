from __future__ import annotations

import os
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone

from . import runtime_v2 as v2
from . import runtime_v6 as v6
from .fresh_x import is_fresh_iran_topic
from .persian_editor import edit_news_text, is_promotional_news_text

_easy_news_flow_installed = False
_original_strict_rejection = v2._strict_rejection_reason
_original_translate = v2.translate_news_to_fa
_X_STATUS_RE = re.compile(r"^https?://(?:www\.)?(?:x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(?:[/?#].*)?$", re.I)
_WEB_LINK_RE = re.compile(r"^https?://", re.I)
_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")
_LATIN_WORD_RE = re.compile(r"\b[A-Za-z]{2,}\b")
_FLAG_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")
_VISUAL_EMOJI_RE = re.compile(r"[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")
_translation_cache: dict[str, str] = {}

_TOPIC_ICONS = (
    ("🚀", ("missile", "rocket", "موشک", "راکت")),
    ("🛸", ("drone", "uav", "پهپاد")),
    ("💥", ("strike", "attack", "explosion", "blast", "bomb", "حمله", "انفجار", "بمباران")),
    ("💨", ("smoke", "fire", "burning", "دود", "آتش", "حریق")),
    ("🚢", ("ship", "tanker", "vessel", "navy", "کشتی", "نفتکش", "شناور", "ناو")),
    ("✈️", ("aircraft", "airplane", "flight", "airspace", "هواپیما", "پرواز", "حریم هوایی")),
    ("🛢️", ("oil", "crude", "petroleum", "نفت", "نفت خام")),
    ("☢️", ("nuclear", "uranium", "enrichment", "iaea", "هسته", "اورانیوم", "غنی‌سازی", "آژانس")),
    ("⚓", ("hormuz", "strait", "هرمز", "تنگه")),
    ("🕊️", ("ceasefire", "talks", "negotiation", "deal", "آتش‌بس", "مذاکره", "توافق")),
)

_EXTRA_COUNTRY_FLAGS = (
    ("🇾🇪", ("yemen", "yemeni", "houthi", "houthis", "یمن", "یمنی", "حوثی")),
    ("🇵🇸", ("palestine", "palestinian", "gaza", "west bank", "فلسطین", "فلسطینی", "غزه", "کرانه باختری")),
    ("🇸🇾", ("syria", "syrian", "damascus", "سوریه", "سوری", "دمشق")),
    ("🇹🇷", ("turkey", "turkish", "ankara", "ترکیه", "ترک", "آنکارا")),
    ("🇵🇰", ("pakistan", "pakistani", "islamabad", "پاکستان", "پاکستانی", "اسلام‌آباد")),
    ("🇦🇫", ("afghanistan", "afghan", "kabul", "افغانستان", "افغان", "کابل")),
)


def _is_x_item(item) -> bool:
    return str(getattr(item, "source", "")).endswith(" / X")


def _is_telegram_item(item) -> bool:
    source = str(getattr(item, "source", ""))
    return source.endswith(" / Telegram") or source.endswith(" / تلگرام")


def _published_dt(item):
    return v2.base.agent._published_dt(getattr(item, "published", "")) or datetime.min.replace(tzinfo=timezone.utc)


def _source_text_for_editor(item) -> str:
    summary = str(getattr(item, "summary", "") or "").strip()
    title = str(getattr(item, "title", "") or "").strip()
    if _is_telegram_item(item) and summary:
        return summary
    return title


def _edited_title(item) -> str:
    raw = _source_text_for_editor(item)
    translated = _translate_or_original(raw)
    if not translated:
        return ""
    edited = edit_news_text(raw, translated)
    if not edited:
        return ""
    original_title = str(getattr(item, "title", "") or "").strip()
    if original_title:
        _translation_cache[original_title] = edited
    _translation_cache[raw] = edited
    return edited


def _select_one_story(candidates, references):
    """Return every publishable candidate from the current scan; do not hold news for a later cycle."""
    _translation_cache.clear()
    if not candidates:
        return [], []
    ordered = sorted(candidates, key=lambda item: (_is_x_item(item), _published_dt(item)), reverse=True)
    selected = []
    for item in ordered:
        title_fa = _edited_title(item)
        if not title_fa:
            continue
        if not v2._original_news_format(_display_item(item), title_fa, ""):
            continue
        selected.append(item)
    return selected, []


def _has_valid_source_link(item) -> bool:
    link = str(getattr(item, "link", "") or "").strip()
    if not link:
        return False
    if _is_x_item(item):
        return bool(_X_STATUS_RE.match(link))
    return bool(_WEB_LINK_RE.match(link))


def _easy_rejection_reason(item, now):
    if _is_x_item(item):
        if not _has_valid_source_link(item):
            return "missing_direct_source_link"
        if v2.base.agent._published_dt(getattr(item, "published", "")) is None:
            return "invalid_publish_time"
        if not v2.base.agent._published_today(getattr(item, "published", ""), now):
            return "not_today_tehran"
        raw = f"{getattr(item, 'title', '')} {getattr(item, 'summary', '')}"
        if not is_fresh_iran_topic(raw):
            return "not_iran_related"
        if is_promotional_news_text(raw):
            return "promotional_or_non_news"
        return None
    return _original_strict_rejection(item, now)


def _is_persian_output(value: str) -> bool:
    text = str(value or "").strip()
    if not text or _HEBREW_RE.search(text):
        return False
    persian_letters = re.findall(r"[\u0600-\u06FF]", text)
    latin_letters = re.findall(r"[A-Za-z]", text)
    letter_count = len(persian_letters) + len(latin_letters)
    if len(persian_letters) < 4 or letter_count == 0:
        return False
    return len(persian_letters) / letter_count >= 0.55


def _persian_digits(value: str) -> str:
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _repair_precise_translation(source: str, translated: str) -> str:
    source_l = re.sub(r"\s+", " ", str(source or "").lower()).strip()
    tanker = re.search(r"\b(\d+)\s+tankers?\s+(?:above|near|around)\s+(?:the\s+)?strait of hormuz\b", source_l)
    qatar_israel = re.search(r"\b(\d+)\s+from qatar\s*[,;]\s*(\d+)\s+from israel\b", source_l)
    if tanker and qatar_israel:
        total = _persian_digits(tanker.group(1))
        qatar = _persian_digits(qatar_israel.group(1))
        israel = _persian_digits(qatar_israel.group(2))
        return f"{total} نفتکش در محدوده تنگه هرمز؛ {qatar} نفتکش از قطر و {israel} نفتکش از اسرائیل."
    return str(translated or "").strip()


def _translate_or_original(value, session=None):
    text = str(value or "").strip()
    if not text:
        return ""
    cached = _translation_cache.get(text)
    if cached:
        return cached
    try:
        translated = str(_original_translate(text, session=session) or "").strip()
    except Exception:
        translated = ""
    translated = _repair_precise_translation(text, translated)
    if translated and _is_persian_output(translated):
        _translation_cache[text] = translated
        return translated
    if _is_persian_output(text):
        _translation_cache[text] = text
        return text
    return ""


def _strip_visual_emojis(value: str) -> str:
    text = _VISUAL_EMOJI_RE.sub(" ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[\s\-–—:|]+", "", text).strip()
    return text


def _display_item(item):
    source = str(getattr(item, "source", "") or "")
    display_source = source.replace(" / Telegram", " / تلگرام").replace(" / X", " / ایکس")
    return replace(item, source=display_source) if display_source != source else item


def _topic_icons(item, title_fa: str, summary_fa: str) -> str:
    text = f" {item.title} {item.summary} {title_fa} {summary_fa} ".lower()
    icons = [icon for icon, terms in _TOPIC_ICONS if any(term in text for term in terms)]
    return " ".join(dict.fromkeys(icons))


def _literal_flags(item) -> list[str]:
    text = f"{getattr(item, 'title', '')} {getattr(item, 'summary', '')}"
    return list(dict.fromkeys(_FLAG_RE.findall(text)))


def _country_flags(item, title_fa: str, summary_fa: str) -> str:
    text = f" {item.title} {item.summary} {title_fa} {summary_fa} ".lower()
    base_flags = v2._country_flags(item, title_fa, summary_fa).split()
    extra = [flag for flag, terms in _EXTRA_COUNTRY_FLAGS if any(term in text for term in terms)]
    return " ".join(dict.fromkeys([*_literal_flags(item), *base_flags, *extra]))


def _format_news_with_footer_icons(item, title_fa: str, summary_fa: str, marker_override=None) -> str:
    if not _has_valid_source_link(item) or not _is_persian_output(title_fa):
        return ""
    if summary_fa and not _is_persian_output(summary_fa):
        summary_fa = ""

    clean_title = _strip_visual_emojis(title_fa)
    clean_summary = _strip_visual_emojis(summary_fa)
    if _LATIN_WORD_RE.search(clean_title) or _LATIN_WORD_RE.search(clean_summary):
        return ""

    display_item = _display_item(item)
    text = v2._original_news_format(display_item, clean_title, clean_summary, marker_override=marker_override)
    if not text:
        return text

    marker_match = re.match(r"^(🛑|🔺|🟥|⚪️)\s+", text)
    marker = marker_match.group(1) if marker_match else ""
    if marker_match:
        text = text[marker_match.end():]
    text = re.sub(r"\n\n(?:▫️|🟥)\s+(?=<b>)", "\n\n", text)
    text = text.replace(" / Telegram", " / تلگرام").replace(" / X", " / ایکس")

    flags = _country_flags(item, clean_title, clean_summary)
    icons = _topic_icons(item, clean_title, clean_summary)
    bottom_parts = []
    if marker and marker != "⚪️":
        bottom_parts.append(marker)
    if flags:
        bottom_parts.extend(flags.split())
    if icons:
        bottom_parts.extend(icons.split())
    bottom = " ".join(dict.fromkeys(bottom_parts))
    if not bottom:
        return text
    return f"{text.rstrip()}\n\n{bottom}"


def install_easy_news_flow() -> None:
    global _easy_news_flow_installed
    if _easy_news_flow_installed:
        return
    v6.install_output_policy()
    v2._strict_rejection_reason = _easy_rejection_reason
    v2.translate_news_to_fa = _translate_or_original
    v2._format_news_with_flags = _format_news_with_footer_icons
    v2.base.agent._news_rejection_reason = _easy_rejection_reason
    v2.base.agent._select_top_stories = _select_one_story
    _easy_news_flow_installed = True


def run(now=None) -> int:
    install_easy_news_flow()
    return v6.run(now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_easy_news_flow()
    return v6.monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
