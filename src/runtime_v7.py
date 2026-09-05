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


def _is_x_item(item) -> bool:
    return str(getattr(item, "source", "")).endswith(" / X")


def _published_dt(item):
    return v2.base.agent._published_dt(getattr(item, "published", "")) or datetime.min.replace(tzinfo=timezone.utc)


def _select_one_story(candidates, references):
    """Publish exactly one newest eligible item per monitor cycle.

    Distinct X status IDs are not semantically deduplicated here. Exact reposts are
    still blocked by the existing news_seen/published-key state before selection.
    """
    if not candidates:
        return [], []
    newest = max(candidates, key=_published_dt)
    return [newest], []


def _has_valid_source_link(item) -> bool:
    link = str(getattr(item, "link", "") or "").strip()
    if not link:
        return False
    if _is_x_item(item):
        return bool(_X_STATUS_RE.match(link))
    return bool(_WEB_LINK_RE.match(link))


def _easy_rejection_reason(item, now):
    # Keep the flow permissive, but never publish a source-less item or an X post
    # that is not directly Iran-related.
    if _is_x_item(item):
        if not _has_valid_source_link(item):
            return "missing_direct_source_link"
        if not is_fresh_iran_topic(f"{getattr(item, 'title', '')} {getattr(item, 'summary', '')}"):
            return "not_iran_related"
        return None
    return _original_strict_rejection(item, now)


def _is_persian_output(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
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
    translated = str(_original_translate(text, session=session) or "").strip()
    if translated and _is_persian_output(translated):
        return translated
    # Persian source posts can pass untouched. English/Hebrew or bad translator
    # fallbacks are withheld and retried instead of leaking into the channel.
    return text if _is_persian_output(text) else ""


def _topic_icons(item, title_fa: str, summary_fa: str) -> str:
    text = f" {item.title} {item.summary} {title_fa} {summary_fa} ".lower()
    icons = [icon for icon, terms in _TOPIC_ICONS if any(term in text for term in terms)]
    return " ".join(dict.fromkeys(icons))


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

    flags = v2._country_flags(item, title_fa, summary_fa)
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
