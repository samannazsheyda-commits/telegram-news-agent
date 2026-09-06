from __future__ import annotations

import html
import os
import re
import sys
from dataclasses import replace

from . import runtime_v7 as v7
from . import runtime_v8 as v8
from .cars import create_car_telegraph_page, format_car_telegraph_post
from .market_policy import market_summary_day, regular_market_allowed

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

    if _LATIN_VISIBLE_RE.search(mapped):
        if source.endswith(" / X"):
            mapped = "منبع در ایکس"
        elif source.endswith(" / Telegram") or source.endswith(" / تلگرام"):
            mapped = "منبع در تلگرام"
        else:
            mapped = "منبع خبری"

    return replace(item, source=mapped) if mapped != source else item


def _visible_text(message: str) -> str:
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
    message = message.replace("👉🏻 ", "").replace("👉 ", "")

    visible = _visible_text(message)
    if _LATIN_VISIBLE_RE.search(visible):
        print(
            f"NEWS_WARNING visible_latin_text source={getattr(item, 'source', '')!r} "
            f"title={getattr(item, 'title', '')!r}"
        )
    return message


def _newsroom_low_value_company_news(item) -> bool:
    """Keep direct Iran security/airspace developments even when airlines are mentioned."""
    text = f"{getattr(item, 'title', '')} {getattr(item, 'summary', '')}".lower()
    if "iran" in text or "iranian" in text or "ایران" in text:
        if any(term in text for term in _AIRSPACE_SECURITY_TERMS):
            return False
    return _original_low_value_company(item)


def _market_quiet_hours(now) -> bool:
    return not regular_market_allowed(now)


def _format_car_via_telegraph(prices, previous=None) -> str:
    """Create an in-Telegram Telegraph page and return only its compact Telegram card."""
    page_url = create_car_telegraph_page(prices, previous or {})
    return format_car_telegraph_post(page_url, len(prices))


def install_persian_only_output() -> None:
    global _installed
    if _installed:
        return
    v7._display_item = _persian_source_item
    v7._format_news_with_footer_icons = _format_persian_only
    v8.install_strict_dedup_policy()
    v7.v2._format_news_with_flags = _format_persian_only
    v7.v2.base.is_low_value_company_news = _newsroom_low_value_company_news
    v7.v2.base.agent._market_quiet_hours = _market_quiet_hours
    v7.v2.base.agent._market_summary_day = market_summary_day
    # Main's daily car job calls this global. Replace it with the Telegraph publisher
    # so the user opens telegra.ph in Telegram Instant View instead of the source site.
    v7.v2.base.agent.format_car_prices = _format_car_via_telegraph
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
