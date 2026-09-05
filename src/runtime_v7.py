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


def _easy_rejection_reason(item, now):
    # Easy flow means almost no editorial blocking, but the channel remains Iran-only.
    # Re-check relevance here even if ingestion already filtered it so a bad upstream
    # row can never leak into production.
    if _is_x_item(item):
        if not is_fresh_iran_topic(f"{getattr(item, 'title', '')} {getattr(item, 'summary', '')}"):
            return "not_iran_related"
        return None
    return _original_strict_rejection(item, now)


def _looks_persian(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", value or ""))


def _translate_or_original(value, session=None):
    text = str(value or "").strip()
    translated = _original_translate(text, session=session)
    if translated:
        return translated
    # Persian text is safe to keep as-is. Never leak Hebrew/English/other foreign
    # source text into the Persian channel when translation fails.
    return text if _looks_persian(text) else ""


def _topic_icons(item, title_fa: str, summary_fa: str) -> str:
    text = f" {item.title} {item.summary} {title_fa} {summary_fa} ".lower()
    icons = [icon for icon, terms in _TOPIC_ICONS if any(term in text for term in terms)]
    return " ".join(dict.fromkeys(icons))


def _format_news_with_footer_icons(item, title_fa: str, summary_fa: str, marker_override=None) -> str:
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
