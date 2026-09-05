from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime

import requests

from . import formatters
from .news_output import clean_visible_x_text
from .newsroom_x import builtin_x_news_sources, is_monitored_x_topic
from .sources import NewsItem, USER_AGENT

FXTWITTER_TIMELINE = "https://api.fxtwitter.com/2/profile/{handle}/statuses"

# Extra first-party / high-signal accounts for the near-realtime Iran monitor.
# CENTCOM, White House, State Department, State spokesperson, SecRubio, SecDef,
# Treasury, VP and IDF are already included by builtin_x_news_sources().
_EXTRA_X_SOURCES = (
    {"name": "Barak Ravid", "handle": "@BarakRavid"},
    {"name": "Abbas Araghchi", "handle": "@araghchi"},
    {"name": "Mohsen Rezaei", "handle": "@ir_rezaee"},
    {"name": "Sepah News", "handle": "@Sepah_News"},
    {"name": "TankerTrackers", "handle": "@TankerTrackers"},
    {"name": "White House Press Secretary", "handle": "@PressSec"},
    {"name": "White House Communications Director", "handle": "@StevenCheung47"},
    {"name": "White House Deputy Press Secretary", "handle": "@ATJackson47"},
    {"name": "White House Rapid Response", "handle": "@RapidResponse47"},
    {"name": "President of the United States", "handle": "@POTUS"},
    {"name": "White House Homeland Security Advisor", "handle": "@StephenM"},
    {"name": "CENTCOM Farsi", "handle": "@CENTCOMFarsi"},
    {"name": "USA Beh Farsi", "handle": "@USABehFarsi"},
    {"name": "US Mission to the UN", "handle": "@USUN"},
    {"name": "US Mission to the UN Vienna", "handle": "@usunvie"},
    {"name": "US National Intelligence", "handle": "@ODNIgov"},
    {"name": "State Department Counterterrorism", "handle": "@StateDeptCT"},
    {"name": "Iran Foreign Ministry", "handle": "@MFAIRAN"},
    {"name": "Khamenei.ir", "handle": "@khamenei_ir"},
)

_EXTRA_SOURCE_FA = {
    "Barak Ravid / X": "باراک راوید / ایکس",
    "Abbas Araghchi / X": "عباس عراقچی / ایکس",
    "Mohsen Rezaei / X": "محسن رضایی / ایکس",
    "Sepah News / X": "سپاه نیوز",
    "TankerTrackers / X": "تانکرترکرز / ایکس",
    "White House Press Secretary / X": "سخنگوی کاخ سفید / ایکس",
    "White House Communications Director / X": "مدیر ارتباطات کاخ سفید / ایکس",
    "White House Deputy Press Secretary / X": "معاون سخنگوی کاخ سفید / ایکس",
    "White House Rapid Response / X": "واکنش سریع کاخ سفید / ایکس",
    "President of the United States / X": "رئیس‌جمهور آمریکا / ایکس",
    "White House Homeland Security Advisor / X": "مشاور امنیت داخلی کاخ سفید / ایکس",
    "CENTCOM Farsi / X": "سنتکام فارسی / ایکس",
    "USA Beh Farsi / X": "وزارت خارجه آمریکا به فارسی / ایکس",
    "US Mission to the UN / X": "نمایندگی آمریکا در سازمان ملل / ایکس",
    "US Mission to the UN Vienna / X": "نمایندگی آمریکا در وین / ایکس",
    "US National Intelligence / X": "جامعه اطلاعاتی آمریکا / ایکس",
    "State Department Counterterrorism / X": "دفتر ضدتروریسم وزارت خارجه آمریکا / ایکس",
    "Iran Foreign Ministry / X": "وزارت خارجه ایران / ایکس",
    "Khamenei.ir / X": "خامنه‌ای دات‌آی‌آر / ایکس",
}
for _key, _value in _EXTRA_SOURCE_FA.items():
    formatters.SOURCE_FA.setdefault(_key, _value)

# Broad words such as "sanctions", "missile" or "nuclear" are useful secondary
# topic signals, but are not enough by themselves: otherwise unrelated Cuba/Ukraine
# posts leak into an Iran-only channel. At least one Iran anchor must also be present.
_IRAN_ANCHORS = (
    "iran", "iranian", "tehran", "irgc", "quds force", "sepah", "hormuz",
    "persian gulf", "kharg", "fordow", "natanz", "isfahan nuclear", "arak reactor",
    "ایران", "ایرانی", "تهران", "سپاه", "نیروی قدس", "هرمز", "خلیج فارس",
    "خارک", "فردو", "نطنز", "تأسیسات اصفهان", "راکتور اراک",
)

# The Telegram newsroom currently publishes X items as text + source link only.
# If the claim explicitly depends on watching a video/clip/footage, publishing only
# the prose is misleading and incomplete. Suppress it until the media itself can be
# attached to the Telegram post.
_VIDEO_DEPENDENT_RE = re.compile(r"\b(?:video|footage|clip)\b|ویدیو|ويديو|تصاویر\s+ویدیویی", re.IGNORECASE)


def monitored_x_sources() -> tuple[dict[str, str], ...]:
    merged: dict[str, dict[str, str]] = {}
    for source in (*builtin_x_news_sources(), *_EXTRA_X_SOURCES):
        key = source["handle"].lstrip("@").lower()
        merged.setdefault(key, source)
    return tuple(merged.values())


def is_fresh_iran_topic(text: str) -> bool:
    value = (text or "").lower()
    return is_monitored_x_topic(value) and any(anchor in value for anchor in _IRAN_ANCHORS)


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
        if author_handle and author_handle != expected:
            continue
        canonical_prefix = f"https://x.com/{screen_name}/status/".lower()
        if url and not url.lower().startswith(canonical_prefix):
            continue

        text = clean_visible_x_text(str(row.get("text") or row.get("full_text") or ""))
        published = _normalise_created_at(row.get("created_at"))
        if not text or not published or not is_fresh_iran_topic(text):
            continue
        if _VIDEO_DEPENDENT_RE.search(text):
            print(f"NEWS_SUPPRESSED video_without_channel_media source={source!r} post_id={post_id!r}")
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
    """Fetch monitored X timelines through the public FxTwitter proxy, not X API."""
    merged: dict[str, NewsItem] = {}
    sources = monitored_x_sources()
    failures = 0
    for source in sources:
        try:
            items = fetch_profile_timeline(source, session=session)
        except Exception as exc:
            failures += 1
            print(f"Fresh X timeline error source={source['handle']!r} error={exc}")
            continue
        for item in items:
            merged.setdefault(item.key, item)
    print(f"FRESH_X_SCAN sources={len(sources)} failures={failures} iran_posts={len(merged)}")
    return list(merged.values())
