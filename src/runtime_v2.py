from __future__ import annotations

import re
import sys
from datetime import datetime

from . import runtime as base
from . import services
from .news_context import fetch_news_detail_enriched
from .newsroom_x import fetch_builtin_x_news_items


_original_generic_fetch = base._original_fetch_news_items
_original_priority_score = base._priority_event_priority
_x_news_keys: set[str] = set()


def translate_news_to_fa(text: str) -> str:
    """Translate mixed English/Persian headlines instead of accepting them as Persian."""
    value = (text or "").strip()
    if not value:
        return ""
    latin_words = re.findall(r"\b[A-Za-z]{3,}\b", value)
    words = re.findall(r"[A-Za-z\u0600-\u06FF]+", value)
    mostly_latin = bool(latin_words) and (not words or len(latin_words) / len(words) > 0.30)
    if not mostly_latin:
        return services.translate_to_fa(value)

    for translator in (services._google_translate, services._mymemory_translate):
        try:
            translated = services._polish_fa(translator(value))
            translated = services._repair_news_idioms(value, translated)
            if services._translation_quality_ok(value, translated):
                return translated
        except Exception:
            continue
    return ""


def _x_first_fetch_news_items():
    global _x_news_keys
    try:
        x_items = fetch_builtin_x_news_items()
    except Exception as exc:
        print(f"Newsroom X source error: {exc}", file=sys.stderr)
        x_items = []
    _x_news_keys = {item.key for item in x_items}

    merged = {item.key: item for item in x_items}
    for item in _original_generic_fetch():
        merged.setdefault(item.key, item)
    return list(merged.values())


def _strict_rejection_reason(item, now: datetime):
    # Publication is only for the current Iran-calendar news cycle. Priority
    # searches may use older material for context, but cannot republish it as fresh.
    return base._original_news_rejection_reason(item, now)


def _priority_event_priority(item) -> int:
    score = _original_priority_score(item)
    if item.key in _x_news_keys or item.source.endswith(" / X"):
        score = max(score, 85)
    return score


def install_integrations() -> None:
    base._original_fetch_news_items = _x_first_fetch_news_items
    base._priority_rejection_reason = _strict_rejection_reason
    base._priority_event_priority = _priority_event_priority
    base.agent.fetch_news_detail = fetch_news_detail_enriched
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
