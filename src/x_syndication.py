from __future__ import annotations

import json
import re
from email.utils import format_datetime
from datetime import datetime, timezone

import requests

from .sources import NewsItem, USER_AGENT

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _twitter_dt(value: str) -> str:
    dt = datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
    return format_datetime(dt.astimezone(timezone.utc))


def _walk_tweets(value):
    if isinstance(value, dict):
        if "tweet" in value and isinstance(value["tweet"], dict):
            yield value["tweet"]
        for child in value.values():
            yield from _walk_tweets(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_tweets(child)


def parse_profile_timeline(html: str, handle: str, source_label: str) -> list[NewsItem]:
    from .newsroom_x import clean_x_post_text, is_monitored_x_topic

    match = _NEXT_DATA_RE.search(html or "")
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except Exception:
        return []

    result: list[NewsItem] = []
    seen: set[str] = set()
    for tweet in _walk_tweets(payload):
        tweet_id = str(tweet.get("id_str") or tweet.get("id") or "").strip()
        text = clean_x_post_text(str(tweet.get("full_text") or tweet.get("text") or "").strip())
        created = str(tweet.get("created_at") or "").strip()
        if not tweet_id or not text or not created or tweet_id in seen:
            continue
        if not is_monitored_x_topic(text):
            continue
        user = tweet.get("user") or {}
        screen_name = str(user.get("screen_name") or handle).lstrip("@")
        try:
            published = _twitter_dt(created)
        except Exception:
            continue
        seen.add(tweet_id)
        result.append(
            NewsItem(
                f"x:{screen_name.lower()}:{tweet_id}",
                source_label,
                text,
                "",
                f"https://x.com/{screen_name}/status/{tweet_id}",
                published,
            )
        )
    return result


def fetch_profile_timeline(handle: str, source_label: str, session=requests) -> list[NewsItem]:
    screen_name = handle.lstrip("@")
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{screen_name}"
    response = session.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=12,
    )
    response.raise_for_status()
    return parse_profile_timeline(response.text, screen_name, source_label)
