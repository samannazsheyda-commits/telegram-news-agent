from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .custom_sources import (
    CUSTOM_SOURCES_PATH,
    _fetch_x_items,
    _news_key,
    _read_sources,
    discover_feed_url,
    normalize_telegram_channel,
    parse_public_feed,
)
from .persian_editor import trim_to_complete_sentences
from .sources import NewsItem, USER_AGENT, is_iran_related, strip_html

PRIORITY_TERMS = (
    "missile", "ballistic", "cruise missile", "rocket", "launch", "intercept", "siren",
    "strike", "attack", "explosion", "blast", "bombing", "hormuz", "strait of hormuz",
    "tanker", "warship", "drone", "air defense",
    "موشک", "بالستیک", "کروز", "شلیک", "رهگیری", "آژیر", "حمله", "انفجار", "بمباران",
    "هرمز", "نفتکش", "ناو", "پهپاد", "پدافند",
)
REGION_TERMS = (
    "iran", "iranian", "tehran", "irgc", "israel", "israeli", "jordan", "iraq", "kuwait",
    "bahrain", "qatar", "uae", "emirates", "oman", "saudi", "gulf", "hormuz", "middle east",
    "ایران", "تهران", "سپاه", "اسرائیل", "اردن", "عراق", "کویت", "بحرین", "قطر", "امارات",
    "عمان", "عربستان", "خلیج", "هرمز",
)


def _priority_relevant(text: str) -> bool:
    raw = str(text or "")
    without_provenance = re.sub(r"(?i)(?:#\s*)?iran(?:ian)?\s*[-–—]?\s*made\b", " ", raw)
    if is_iran_related(without_provenance):
        return True
    lowered = raw.lower()
    return any(term in lowered for term in PRIORITY_TERMS) and any(term in lowered for term in REGION_TERMS)


def _parse_telegram(html_text: str, channel: str, source_name: str) -> list[NewsItem]:
    channel = normalize_telegram_channel(channel)
    soup = BeautifulSoup(html_text or "", "html.parser")
    display = f"{source_name} / Telegram"
    out: list[NewsItem] = []
    for message in soup.select(".tgme_widget_message[data-post]"):
        data_post = str(message.get("data-post") or "")
        if not data_post.lower().startswith(channel.lower() + "/"):
            continue
        text_node = message.select_one(".tgme_widget_message_text")
        text = strip_html(str(text_node)) if text_node is not None else ""
        if not text or not _priority_relevant(text):
            continue
        title = re.sub(r"\s+", " ", text).strip()
        if len(title) > 300:
            title = trim_to_complete_sentences(title, max_chars=300)
        if not title:
            continue
        published = ""
        time_node = message.select_one("time[datetime]")
        if time_node is not None:
            try:
                dt = datetime.fromisoformat(str(time_node.get("datetime") or "").replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                published = format_datetime(dt.astimezone(timezone.utc))
            except ValueError:
                pass
        link = f"https://t.me/{data_post}"
        out.append(NewsItem(_news_key(display, f"{data_post}:{text}"), display, title, text, link, published))
    return out


def _fetch_telegram_source(source: dict, session=requests) -> list[NewsItem]:
    channel = normalize_telegram_channel(str(source.get("channel") or source.get("url") or ""))
    response = session.get(f"https://t.me/s/{channel}", headers={"User-Agent": USER_AGENT}, timeout=12)
    response.raise_for_status()
    return _parse_telegram(response.text, channel, str(source.get("name") or channel))


def fetch_priority_telegram_realtime(path: str | Path = CUSTOM_SOURCES_PATH, session=requests) -> list[NewsItem]:
    sources = [
        row for row in _read_sources(Path(path))
        if row.get("active", True) and row.get("kind") == "telegram" and str(row.get("status") or "").lower() != "reference"
    ]
    merged: dict[str, NewsItem] = {}
    ok = failed = 0
    if not sources:
        print("DIRECT_TELEGRAM items=0 sources_ok=0 failed=0", flush=True)
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(sources)), thread_name_prefix="bikhabar-telegram") as pool:
        futures = {pool.submit(_fetch_telegram_source, source, session): source for source in sources}
        for future in as_completed(futures):
            try:
                for item in future.result() or []:
                    merged.setdefault(item.key, item)
                ok += 1
            except Exception as exc:
                failed += 1
                source = futures[future]
                print(f"DIRECT_TELEGRAM_FAILED source={source.get('name')!r} error={type(exc).__name__}:{exc}", flush=True)
    print(f"DIRECT_TELEGRAM items={len(merged)} sources_ok={ok} failed={failed}", flush=True)
    return list(merged.values())


def _fetch_nontelegram_source(source: dict, session=requests) -> list[NewsItem]:
    kind = source.get("kind")
    if kind == "website":
        feed_url = str(source.get("feed_url") or "")
        if not feed_url:
            feed_url = discover_feed_url(str(source.get("website_url") or ""), session=session)
        if not feed_url:
            return []
        response = session.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=12)
        response.raise_for_status()
        return parse_public_feed(response.content, str(source.get("name") or "Custom Source"))
    if kind == "x":
        return _fetch_x_items(source, session=session)
    return []


def fetch_custom_nontelegram_realtime(path: str | Path = CUSTOM_SOURCES_PATH, session=requests) -> list[NewsItem]:
    sources = [
        row for row in _read_sources(Path(path))
        if row.get("active", True) and row.get("kind") in {"website", "x"} and str(row.get("status") or "").lower() != "reference"
    ]
    merged: dict[str, NewsItem] = {}
    if not sources:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(sources)), thread_name_prefix="bikhabar-custom") as pool:
        futures = [pool.submit(_fetch_nontelegram_source, source, session) for source in sources]
        for future in as_completed(futures):
            try:
                for item in future.result() or []:
                    merged.setdefault(item.key, item)
            except Exception:
                continue
    return list(merged.values())
