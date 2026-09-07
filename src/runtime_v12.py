from __future__ import annotations

import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from . import runtime_v11 as v11
from .editorial_store import ReviewItem
from .sources import USER_AGENT

base = v11.base
_installed = False
_previous_selector = None
_OWN_CHANNEL = "bikhabaar"


def _normalise_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.rstrip("/")
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    path = re.sub(r"/+", "/", parts.path).rstrip("/")
    if host in {"www.t.me", "telegram.me", "www.telegram.me"}:
        host = "t.me"
    return urlunsplit((scheme, host, path, parts.query, ""))


def extract_public_telegram_source_links(html_text: str, channel: str = _OWN_CHANNEL) -> set[str]:
    """Extract original-source links embedded in published posts of our own channel.

    The public Telegram page contains both the original source link and the channel
    branding link. Only anchors whose label explicitly identifies them as a source
    are authoritative dedup references.
    """
    channel = (channel or "").strip().lstrip("@").lower()
    soup = BeautifulSoup(html_text or "", "html.parser")
    found: set[str] = set()
    for message in soup.select(".tgme_widget_message[data-post]"):
        data_post = str(message.get("data-post") or "").lower()
        if not data_post.startswith(channel + "/"):
            continue
        for anchor in message.select(".tgme_widget_message_text a[href]"):
            label = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).lower()
            if "منبع" not in label and "source" not in label:
                continue
            href = _normalise_url(str(anchor.get("href") or ""))
            if not href:
                continue
            own = _normalise_url(f"https://t.me/{channel}")
            if href == own or href.startswith(own + "/"):
                continue
            found.add(href)
    return found


def _fetch_own_channel_source_links(session=requests) -> set[str]:
    try:
        response = session.get(
            f"https://t.me/s/{_OWN_CHANNEL}",
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        response.raise_for_status()
        return extract_public_telegram_source_links(response.text, _OWN_CHANNEL)
    except Exception as exc:
        print(f"OWN_CHANNEL_DEDUP fetch_error={exc}", file=sys.stderr)
        return set()


def _seed_published_history(item) -> None:
    """Turn a direct/manual channel publication into an authoritative history ref.

    We use the original incoming item here, so later reports from other outlets can
    be compared in the original language by runtime_v11's semantic dedup logic.
    """
    now = datetime.now(timezone.utc).isoformat()
    review = ReviewItem.for_news(
        news_key=str(item.key or ""),
        source=str(item.source or ""),
        source_url=str(item.link or ""),
        original_title=str(item.title or ""),
        original_summary=str(item.summary or ""),
        published_at_source=str(item.published or ""),
        rejection_reason="published_in_channel",
        status="published_manual",
        decision_at=now,
        updated_at=now,
    )
    base._store.upsert_history(review)


def _select_top_stories_with_own_channel(candidates, references):
    channel_links = {_normalise_url(link) for link in _fetch_own_channel_source_links() if link}
    fresh = []
    skipped = []
    for item in candidates:
        source_link = _normalise_url(str(getattr(item, "link", "") or ""))
        if source_link and source_link in channel_links:
            skipped.append(item)
            try:
                _seed_published_history(item)
            except Exception as exc:
                print(f"OWN_CHANNEL_DEDUP history_error key={getattr(item, 'key', '')!r} error={exc}", file=sys.stderr)
            print(
                f"NEWS_SUPPRESSED published_channel_duplicate source={getattr(item, 'source', '')!r} "
                f"link={getattr(item, 'link', '')!r} title={getattr(item, 'title', '')!r}"
            )
            continue
        fresh.append(item)

    selector = _previous_selector or v11._select_top_stories_with_published_history
    selected, normal_skipped = selector(fresh, references)
    return selected, skipped + normal_skipped


def install_production_policies() -> None:
    global _installed, _previous_selector
    if _installed:
        return
    v11.install_production_policies()
    _previous_selector = base.agent._select_top_stories
    base.agent._select_top_stories = _select_top_stories_with_own_channel
    _installed = True


def run(now=None) -> int:
    install_production_policies()
    resolved_now = now or datetime.now(timezone.utc)
    v11.v10._retry_todays_false_bundles(resolved_now)
    v11.v10._publish_daily_flagships(resolved_now)
    return v11.v10.v9.run(resolved_now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
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
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(v11.v10.os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(v11.v10.os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
