from __future__ import annotations

import re
import sys
from datetime import datetime

from . import runtime as base
from . import services
from . import sources
from .news_context import fetch_news_detail_enriched
from .newsroom_x import fetch_builtin_x_news_items


_original_generic_fetch = base._original_fetch_news_items
_original_custom_fetch = base.fetch_custom_news_items
_original_priority_score = base._priority_event_priority
_x_news_keys: set[str] = set()

_X_SOURCE_FA = {
    "Reuters / X": "رویترز / ایکس",
    "Associated Press / X": "آسوشیتدپرس / ایکس",
    "AFP / X": "خبرگزاری فرانسه / ایکس",
    "BBC World / X": "بی‌بی‌سی ورلد / ایکس",
    "CNN / X": "سی‌ان‌ان / ایکس",
    "France 24 / X": "فرانس ۲۴ / ایکس",
    "Al Jazeera English / X": "الجزیره انگلیسی / ایکس",
    "Al Arabiya English / X": "العربیه انگلیسی / ایکس",
    "Times of Israel / X": "تایمز اسرائیل / ایکس",
    "Haaretz / X": "هاآرتص / ایکس",
    "Axios / X": "اکسیوس / ایکس",
}
base.news_formatters.SOURCE_FA.update(_X_SOURCE_FA)

_PRESERVED_SPECIAL_SOURCES = {
    "Barak Ravid / X",
    "Abbas Araghchi / X",
    "Mohsen Rezaei / X",
    "Sepah News / X",
    "TankerTrackers",
    "NOTAM / Airspace",
}


def translate_news_to_fa(text: str, session=None) -> str:
    """Translate mixed English/Persian headlines instead of accepting them as Persian."""
    value = (text or "").strip()
    if not value:
        return ""
    latin_words = re.findall(r"\b[A-Za-z]{3,}\b", value)
    words = re.findall(r"[A-Za-z\u0600-\u06FF]+", value)
    mostly_latin = bool(latin_words) and (not words or len(latin_words) / len(words) > 0.30)
    if not mostly_latin:
        return services.translate_to_fa(value, session=session or services.requests)

    translation_session = session or services.requests
    for translator in (services._google_translate, services._mymemory_translate):
        try:
            translated = services._polish_fa(translator(value, session=translation_session))
            translated = services._repair_news_idioms(value, translated)
            if services._translation_quality_ok(value, translated):
                return translated
        except Exception:
            continue
    return ""


def _x_first_fetch_news_items():
    """Fetch only the official newsroom X stream, never the newsroom websites."""
    global _x_news_keys
    try:
        x_items = fetch_builtin_x_news_items()
    except Exception as exc:
        print(f"Newsroom X source error: {exc}", file=sys.stderr)
        x_items = []
    _x_news_keys = {item.key for item in x_items}
    return list(x_items)


def _fetch_preserved_special_items() -> list:
    merged = {}
    for source_name, query, lang in sources.SPECIAL_QUERIES:
        if source_name not in _PRESERVED_SPECIAL_SOURCES:
            continue
        try:
            items = sources._fetch_google_news_query(
                sources.requests,
                source_name,
                query,
                lang,
                allow_special_source=True,
            )
        except Exception as exc:
            print(f"Special source error ({source_name}): {exc}", file=sys.stderr)
            continue
        for item in items:
            merged.setdefault(item.key, item)
    return list(merged.values())


def _custom_x_and_alert_items() -> list:
    merged = {item.key: item for item in _fetch_preserved_special_items()}
    try:
        custom_items = _original_custom_fetch()
    except Exception as exc:
        print(f"Custom X source error: {exc}", file=sys.stderr)
        custom_items = []
    for item in custom_items:
        if item.source.endswith(" / X"):
            merged.setdefault(item.key, item)
    return list(merged.values())


def _no_priority_web_news() -> list:
    return []


def _is_newsroom_x(item) -> bool:
    return item.source.endswith(" / X") and item.source not in {
        "Barak Ravid / X",
        "Abbas Araghchi / X",
        "Mohsen Rezaei / X",
        "Sepah News / X",
    }


def _strict_rejection_reason(item, now: datetime):
    if _is_newsroom_x(item):
        if base.agent._published_dt(item.published) is None:
            return "invalid_publish_time"
        if not base.agent._published_today(item.published, now):
            return "not_today_tehran"
        if not base.agent.is_iran_related(f"{item.title} {item.summary}"):
            return "low_signal_or_unapproved_source"
        return None
    return base._original_news_rejection_reason(item, now)


def _priority_event_priority(item) -> int:
    score = _original_priority_score(item)
    if item.key in _x_news_keys or item.source.endswith(" / X"):
        score = max(score, 85)
    return score


def fetch_news_detail_x_only(item, session=None) -> str:
    """Newsroom X items publish the tweet text only; non-X alerts keep normal detail enrichment."""
    if item.source.endswith(" / X"):
        return ""
    if session is None:
        return fetch_news_detail_enriched(item)
    return fetch_news_detail_enriched(item, session=session)


def install_integrations() -> None:
    base._original_fetch_news_items = _x_first_fetch_news_items
    base.fetch_custom_news_items = _custom_x_and_alert_items
    base.fetch_priority_news_items = _no_priority_web_news
    base._priority_rejection_reason = _strict_rejection_reason
    base._priority_event_priority = _priority_event_priority
    base.agent.fetch_news_detail = fetch_news_detail_x_only
    base.agent.translate_to_fa = translate_news_to_fa
    base.install_integrations()


def run(now: datetime | None = None) -> int:
    install_integrations()
    rc = base.agent.run(now)
    if rc == 0:
        try:
            base._send_hormuz_daily(now)
        except Exception as exc:
            print(f"Hormuz daily report error: {exc}", file=sys.stderr)
    base._flush_recent_published(now)
    return rc


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    import time

    poll_seconds = max(1, int(poll_seconds))
    session_seconds = max(poll_seconds, int(session_seconds))
    started = time.monotonic()
    while True:
        cycle_started = time.monotonic()
        if cycle_started - started >= session_seconds:
            return 0
        rc = run()
        if rc != 0:
            return rc
        cycle_finished = time.monotonic()
        if cycle_finished - started + poll_seconds > session_seconds:
            return 0
        time.sleep(max(0.0, poll_seconds - (cycle_finished - cycle_started)))


def _cli() -> int:
    import os

    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
