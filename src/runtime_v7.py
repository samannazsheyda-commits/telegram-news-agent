from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone

from . import runtime_v2 as v2
from . import runtime_v6 as v6
from .fresh_x import is_fresh_iran_topic

_easy_news_flow_installed = False
_original_strict_rejection = v2._strict_rejection_reason
_original_translate = v2.translate_news_to_fa
_RLM = "\u200f"
_X_STATUS_RE = re.compile(r"^https?://(?:www\.)?(?:x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(?:[/?#].*)?$", re.I)
_WEB_LINK_RE = re.compile(r"^https?://", re.I)
_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")
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


def _published_dt(item):
    return v2.base.agent._published_dt(getattr(item, "published", "")) or datetime.min.replace(tzinfo=timezone.utc)


def _select_one_story(candidates, references):
    """Choose up to five publishable candidates, prioritizing X posts first.

    Exact already-published keys are blocked upstream. Distinct X status IDs are not
    semantically deduplicated here. Within each source class, newest items come first.
    If a title cannot be translated or would format to an empty card, skip it and
    continue down the queue in the same cycle.
    """
    _translation_cache.clear()
    if not candidates:
        return [], []
    ordered = sorted(candidates, key=lambda item: (_is_x_item(item), _published_dt(item)), reverse=True)
    selected = []
    for item in ordered:
        title_fa = _translate_or_original(getattr(item, "title", ""))
        if not title_fa:
            continue
        if not v2._original_news_format(item, title_fa, ""):
            continue
        selected.append(item)
        if len(selected) >= 5:
            break
    return selected, []


def _has_valid_source_link(item) -> bool:
    link = str(getattr(item, "link", "") or "").strip()
    if not link:
        return False
    if _is_x_item(item):
        return bool(_X_STATUS_RE.match(link))
    return bool(_WEB_LINK_RE.match(link))


def _easy_rejection_reason(item, now):
    # The feed is permissive on editorial scoring, but not on provenance, freshness,
    # or Iran relevance. Old indexed/timeline rows must never refill the channel.
    if _is_x_item(item):
        if not _has_valid_source_link(item):
            return "missing_direct_source_link"
        if v2.base.agent._published_dt(getattr(item, "published", "")) is None:
            return "invalid_publish_time"
        if not v2.base.agent._published_today(getattr(item, "published", ""), now):
            return "not_today_tehran"
        if not is_fresh_iran_topic(f"{getattr(item, 'title', '')} {getattr(item, 'summary', '')}"):
            return "not_iran_related"
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
    # Allow normal acronyms/names such as IAEA or IRGC, but never an English body
    # containing only one Persian word.
    return len(persian_letters) / letter_count >= 0.55


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
    if translated and _is_persian_output(translated):
        _translation_cache[text] = translated
        return translated
    # Persian source posts can pass untouched. English/Hebrew or bad translator
    # fallbacks are withheld and retried instead of leaking into the channel.
    if _is_persian_output(text):
        _translation_cache[text] = text
        return text
    return ""


def _topic_icons(item, title_fa: str, summary_fa: str) -> str:
    text = f" {item.title} {item.summary} {title_fa} {summary_fa} ".lower()
    icons = [icon for icon, terms in _TOPIC_ICONS if any(term in text for term in terms)]
    return " ".join(dict.fromkeys(icons))


def _country_flags(item, title_fa: str, summary_fa: str) -> str:
    text = f" {item.title} {item.summary} {title_fa} {summary_fa} ".lower()
    base_flags = v2._country_flags(item, title_fa, summary_fa).split()
    extra = [flag for flag, terms in _EXTRA_COUNTRY_FLAGS if any(term in text for term in terms)]
    return " ".join(dict.fromkeys([*base_flags, *extra]))


def _format_news_with_footer_icons(item, title_fa: str, summary_fa: str, marker_override=None) -> str:
    # Every published news card must have a real source URL and a Persian headline.
    # This is the last safety gate before Telegram formatting.
    if not _has_valid_source_link(item) or not _is_persian_output(title_fa):
        return ""
    if summary_fa and not _is_persian_output(summary_fa):
        summary_fa = ""

    text = v2._original_news_format(item, title_fa, summary_fa, marker_override=marker_override)
    if not text:
        return text

    flags = _country_flags(item, title_fa, summary_fa)
    icons = _topic_icons(item, title_fa, summary_fa)
    meta = " ".join(part for part in (flags, icons) if part)
    if not meta:
        return text

    return f"{text.rstrip()}\n\n{_RLM}{meta}"


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
