from __future__ import annotations

import html
import os
import re
import sys
from dataclasses import replace

from . import runtime_v7 as v7
from . import runtime_v8 as v8

_installed = False
_original_v7_formatter = v7._format_news_with_footer_icons
_original_low_value_company = v7.v2.base.is_low_value_company_news
_LATIN_VISIBLE_RE = re.compile(r"\b[A-Za-z]{2,}\b")

_SOURCE_OVERRIDES = {
    "Mark Dubowitz / X": "مارک دوبوویتز / ایکس",
    "John Bolton / X": "جان بولتون / ایکس",
    "Al Jazeera English / X": "الجزیره انگلیسی / ایکس",
    "Al Arabiya English / X": "العربیه انگلیسی / ایکس",
}

_AIRSPACE_SECURITY_TERMS = (
    "airspace", "notam", "flight ban", "avoid iranian airspace", "avoid airspace",
    "aviation agency", "security risk", "military action", "حریم هوایی", "نوتام",
    "هشدار هوانوردی", "خطر امنیتی",
)


def _persian_source_item(item):
    source = str(getattr(item, "source", "") or "")
    mapped = _SOURCE_OVERRIDES.get(source)
    if not mapped:
        mapped = v7.v2.base.news_formatters.SOURCE_FA.get(source, source)
    mapped = mapped.replace(" / Telegram", " / تلگرام").replace(" / X", " / ایکس")
    return replace(item, source=mapped) if mapped != source else item


def _visible_text(message: str) -> str:
    # Remove HTML tags (and therefore href URLs) before enforcing the Persian-only gate.
    return re.sub(r"<[^>]+>", "", html.unescape(message or ""))


def _format_persian_only(item, title_fa: str, summary_fa: str, marker_override=None) -> str:
    message = _original_v7_formatter(
        _persian_source_item(item),
        title_fa,
        summary_fa,
        marker_override=marker_override,
    )
    if not message:
        return ""
    visible = _visible_text(message)
    if _LATIN_VISIBLE_RE.search(visible):
        print(
            f"NEWS_SUPPRESSED visible_latin_text source={getattr(item, 'source', '')!r} "
            f"title={getattr(item, 'title', '')!r}"
        )
        return ""
    return message


def _newsroom_low_value_company_news(item) -> bool:
    """Keep direct Iran security/airspace developments even when airlines are mentioned."""
    text = f"{getattr(item, 'title', '')} {getattr(item, 'summary', '')}".lower()
    if "iran" in text or "iranian" in text or "ایران" in text:
        if any(term in text for term in _AIRSPACE_SECURITY_TERMS):
            return False
    return _original_low_value_company(item)


def install_persian_only_output() -> None:
    global _installed
    if _installed:
        return
    # Patch before v8 installs v7 hooks so the production formatter points to this gate.
    v7._display_item = _persian_source_item
    v7._format_news_with_footer_icons = _format_persian_only
    v8.install_strict_dedup_policy()
    # v7 may already have installed its formatter during v8 setup; force the final gate.
    v7.v2._format_news_with_flags = _format_persian_only
    # The production fetcher resolves this global at runtime; keep security/airspace news.
    v7.v2.base.is_low_value_company_news = _newsroom_low_value_company_news
    _installed = True


def run(now=None) -> int:
    install_persian_only_output()
    return v8.run(now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_persian_only_output()
    return v8.monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
