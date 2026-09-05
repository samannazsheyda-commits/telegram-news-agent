from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime

import requests

from . import formatters
from .newsroom_x import (
    builtin_x_news_sources,
    clean_x_post_text,
    is_monitored_x_topic,
)
from .sources import NewsItem, USER_AGENT

FXTWITTER_TIMELINE = "https://api.fxtwitter.com/2/profile/{handle}/statuses"

_EXTRA_X_SOURCES = (
    {"name": "Barak Ravid", "handle": "@BarakRavid"},
    {"name": "Abbas Araghchi", "handle": "@araghchi"},
    {"name": "Mohsen Rezaei", "handle": "@ir_rezaee"},
    {"name": "Sepah News", "handle": "@Sepah_News"},
    {"name": "TankerTrackers", "handle": "@TankerTrackers"},
)

_EXTRA_SOURCE_FA = {
    "Barak Ravid / X": "باراک راوید / ایکس",
    "Abbas Araghchi / X": "عباس عراقچی / ایکس",
    "Mohsen Rezaei / X": "محسن رضایی / ایکس",
    "Sepah News / X": "سپاه نیوز",
    "TankerTrackers / X": "تانکرترکرز / ایکس",
}
for _key, _value in _EXTRA_SOURCE_FA.items():
    formatters.SOURCE_FA.setdefault(_key, _value)


def monitored_x_sources() -> tuple[dict[str, str], ...]:
    merged: dict[str, dict[str, str]] = {}
    for source in (*builtin_x_news_sources(), *_EXTRA_X_SOURCES):
        handle = source["handle"].lstrip("@").lower()
        merged.setdefault(handle, source)
    return tuple(merged.values())


def _normalise_created_at(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        try:
            dt = datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(timezone.utc))


def parse_fxtwitter_timeline(payload: object, source_name: str, handle: str) -> list[NewsItem]:
    if not isinstance(payload, dict) or payload.get("code") != 200:
        raise ValueError("FxTwitter timeline response is invalid")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("FxTwitter timeline results are missing")

    screen_name = handle.lstrip("@")
    expected = screen_name.lower()
    source = f"{source_name} / X"
    items: list[NewsItem] = []
    seen: set[str] = set()

    for row in results:
        if not isinstance(row, dict) or row.get("type") != "status":
            continue
        post_id = str(row.get("id") or row.get("id_str") or "").strip()
        if not post_id or post_id in seen:
            continue

        author = row.get("author") if isinstance(row.get("author"), dict) else {}
        author_handle = str(author.get("screen_name") or "").strip().lower()
        url = str(row.get("url") or "").strip()
        # A timeline entry must belong to the monitored profile. If author metadata is
        # present, require an exact match; otherwise require the canonical profile URL.
        if author_handle and author_handle != expected:
            continue
        canonical_prefix = f"https://x.com/{screen_name}/status/".lower()
        if url and not url.lower().startswith(canonical_prefix):
            continue

        text = clean_x_post_text(str(row.get("text") or row.get("full_text") or ""))
        published = _normalise_created_at(row.get("created_at"))
        if not text or not published or not is_monitored_x_topic(text):
            continue

        seen.add(post_id)
        items.append(
            NewsItem(
                f"x:{screen_name}:{post_id}",
                source,
                text,
                "",
                f"https://x.com/{screen_name}/status/{post_id}",
                published,
            )
        )
    return items


def fetch_profile_timeline(source: dict[str, str], *, session=requests) -> list[NewsItem]:
    handle = source["handle"].lstrip("@")
    response = session.get(
        FXTWITTER_TIMELINE.format(handle=handle),
        params={"count": 100},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=20,
    )
    response.raise_for_status()
    return parse_fxtwitter_timeline(response.json(), source["name"], source["handle"])


def fetch_fresh_x_news_items(*, session=requests) -> list[NewsItem]:
    """Fetch current monitored X timelines through the public FxTwitter proxy.

    This is not the X API. Each returned item is still anchored to the canonical
    x.com status URL and source timestamp.
    """
    merged: dict[str, NewsItem] = {}
    failures = 0
    for source in monitored_x_sources():
        try:
            items = fetch_profile_timeline(source, session=session)
        except Exception as exc:
            failures += 1
            print(f"Fresh X timeline error source={source['handle']!r} error={exc}")
            continue
        for item in items:
            merged.setdefault(item.key, item)
    print(
        f"FRESH_X_SCAN sources={len(monitored_x_sources())} failures={failures} "
        f"iran_posts={len(merged)}"
    )
    return list(merged.values())
