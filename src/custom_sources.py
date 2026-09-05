from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .persian_editor import trim_to_complete_sentences
from .sources import GOOGLE_NEWS_BASE, NewsItem, USER_AGENT, is_iran_related, strip_html


CUSTOM_SOURCES_PATH = Path(os.environ.get("CUSTOM_SOURCES_PATH", "data/custom_sources.json"))
IRAN_QUERY = "(Iran OR Iranian OR Tehran OR Hormuz OR ایران OR تهران OR هرمز)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_id(kind: str, identity: str) -> str:
    return hashlib.sha1(f"{kind}:{identity.lower()}".encode("utf-8")).hexdigest()


def _news_key(source: str, title: str) -> str:
    normalized = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", (title or "").lower()).strip()
    return hashlib.sha1(f"{source.lower()}:{normalized}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WebsiteSource:
    id: str
    kind: str
    name: str
    website_url: str
    feed_url: str = ""
    active: bool = True
    status: str = "needs_feed"
    last_checked_at: str = ""
    last_error: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class XSource:
    id: str
    kind: str
    handle: str
    name: str
    active: bool = True
    status: str = "best_effort"
    last_checked_at: str = ""
    last_error: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, handle: str, name: str = "") -> "XSource":
        normalized = normalize_x_handle(handle)
        return cls(
            id=_source_id("x", normalized),
            kind="x",
            handle=normalized,
            name=(name or normalized.lstrip("@")),
            updated_at=_now(),
        )


def normalize_x_handle(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        if parsed.netloc.lower() not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            raise ValueError("invalid_x_handle")
        text = parsed.path.strip("/").split("/", 1)[0]
    text = text.lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", text):
        raise ValueError("invalid_x_handle")
    return f"@{text}"


def normalize_telegram_channel(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        if parsed.netloc.lower() not in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
            raise ValueError("invalid_telegram_channel")
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if parts and parts[0] == "s":
            parts = parts[1:]
        text = parts[0] if parts else ""
    text = text.lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", text):
        raise ValueError("invalid_telegram_channel")
    return text


def validate_website_source(name: str, website_url: str, feed_url: str = "") -> WebsiteSource:
    name = re.sub(r"\s+", " ", (name or "").strip())
    parsed = urlparse((website_url or "").strip())
    if not name:
        raise ValueError("source_name_required")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid_website_url")
    normalized_site = parsed.geturl()
    normalized_feed = (feed_url or "").strip()
    if normalized_feed:
        fp = urlparse(normalized_feed)
        if fp.scheme not in {"http", "https"} or not fp.netloc:
            raise ValueError("invalid_feed_url")
    now = _now()
    return WebsiteSource(
        id=_source_id("website", normalized_site),
        kind="website",
        name=name,
        website_url=normalized_site,
        feed_url=normalized_feed,
        status="active" if normalized_feed else "needs_feed",
        updated_at=now,
    )


def discover_feed_url(website_url: str, session=requests) -> str:
    response = session.get(website_url, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup.find_all("link", href=True):
        rel = {str(x).lower() for x in (node.get("rel") or [])}
        feed_type = str(node.get("type") or "").lower()
        if "alternate" in rel and feed_type in {"application/rss+xml", "application/atom+xml", "application/feed+json"}:
            return urljoin(website_url, str(node.get("href")))
    for node in soup.find_all("a", href=True):
        href = str(node.get("href") or "")
        label = node.get_text(" ", strip=True).lower()
        if any(term in f"{href.lower()} {label}" for term in ("rss", "atom", "feed")):
            candidate = urljoin(website_url, href)
            parsed = urlparse(candidate)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return candidate
    return ""


def _child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag in names:
            if tag == "link" and child.get("href"):
                return str(child.get("href") or "").strip()
            return (child.text or "").strip()
    return ""


def parse_public_feed(content: bytes, source_name: str) -> list[NewsItem]:
    root = ET.fromstring(content)
    nodes = list(root.findall(".//item"))
    if not nodes:
        nodes = [n for n in root.iter() if n.tag.rsplit("}", 1)[-1].lower() == "entry"]
    items: list[NewsItem] = []
    for node in nodes:
        title = strip_html(_child_text(node, ("title",)))
        summary = strip_html(_child_text(node, ("description", "summary", "content")))
        link = _child_text(node, ("link", "guid", "id"))
        published = _child_text(node, ("pubdate", "published", "updated", "date"))
        if not title or not is_iran_related(f"{title} {summary}"):
            continue
        items.append(NewsItem(_news_key(source_name, title), source_name, title, summary, link, published))
    return items


def _direct_iran_telegram_relevance(text: str) -> bool:
    if not is_iran_related(text):
        return False
    without_provenance = re.sub(
        r"(?i)(?:#\s*)?iran(?:ian)?\s*[-–—]?\s*made\b",
        " ",
        text or "",
    )
    return is_iran_related(without_provenance)


def parse_public_telegram_channel(html_text: str, channel: str, source_name: str) -> list[NewsItem]:
    channel = normalize_telegram_channel(channel)
    soup = BeautifulSoup(html_text or "", "html.parser")
    display = f"{source_name} / Telegram"
    result: list[NewsItem] = []
    for message in soup.select(".tgme_widget_message[data-post]"):
        data_post = str(message.get("data-post") or "")
        if not data_post.lower().startswith(channel.lower() + "/"):
            continue
        text_node = message.select_one(".tgme_widget_message_text")
        text = strip_html(str(text_node)) if text_node is not None else ""
        if not text or not _direct_iran_telegram_relevance(text):
            continue
        title = re.sub(r"\s+", " ", text).strip()
        if len(title) > 240:
            title = trim_to_complete_sentences(title, max_chars=240)
            if not title:
                continue
        time_node = message.select_one("time[datetime]")
        published = ""
        if time_node is not None:
            raw_dt = str(time_node.get("datetime") or "")
            try:
                dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                published = format_datetime(dt.astimezone(timezone.utc))
            except ValueError:
                published = ""
        link = f"https://t.me/{data_post}"
        result.append(NewsItem(_news_key(display, f"{data_post}:{text}"), display, title, text, link, published))
    return result


def _read_sources(path: Path = CUSTOM_SOURCES_PATH) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _write_sources(records: list[dict[str, Any]], path: Path = CUSTOM_SOURCES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class LocalCustomSourceStore:
    def __init__(self, path: str | Path = CUSTOM_SOURCES_PATH):
        self.path = Path(path)

    def all(self) -> list[dict[str, Any]]:
        return _read_sources(self.path)

    def upsert(self, source: WebsiteSource | XSource) -> dict[str, Any]:
        record = asdict(source)
        records = [r for r in self.all() if r.get("id") != source.id]
        records.insert(0, record)
        _write_sources(records, self.path)
        return record

    def delete(self, source_id: str) -> bool:
        records = self.all()
        filtered = [r for r in records if r.get("id") != source_id]
        if len(filtered) == len(records):
            return False
        _write_sources(filtered, self.path)
        return True

    def set_active(self, source_id: str, active: bool) -> dict[str, Any]:
        records = self.all()
        target = None
        for record in records:
            if record.get("id") == source_id:
                record["active"] = bool(active)
                record["updated_at"] = _now()
                target = record
                break
        if target is None:
            raise KeyError(source_id)
        _write_sources(records, self.path)
        return target


def _fetch_x_items(source: dict[str, Any], session=requests) -> list[NewsItem]:
    handle = normalize_x_handle(str(source.get("handle") or ""))
    query = f'{IRAN_QUERY} site:x.com/{handle.lstrip("@")} '
    response = session.get(
        GOOGLE_NEWS_BASE,
        params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    result: list[NewsItem] = []
    display = str(source.get("name") or handle.lstrip("@")) + " / X"
    for node in root.findall(".//item"):
        title = strip_html(_child_text(node, ("title",)))
        summary = strip_html(_child_text(node, ("description",)))
        link = _child_text(node, ("link", "guid"))
        published = _child_text(node, ("pubdate",))
        if not is_iran_related(f"{title} {summary}"):
            continue
        result.append(NewsItem(_news_key(display, title), display, title, summary, link, published))
    return result


def _fetch_telegram_items(source: dict[str, Any], session=requests) -> list[NewsItem]:
    channel = normalize_telegram_channel(str(source.get("channel") or source.get("url") or ""))
    response = session.get(
        f"https://t.me/s/{channel}",
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    return parse_public_telegram_channel(response.text, channel, str(source.get("name") or channel))


def fetch_custom_news_items(path: str | Path = CUSTOM_SOURCES_PATH, session=requests) -> list[NewsItem]:
    merged: dict[str, NewsItem] = {}
    for source in _read_sources(Path(path)):
        if not source.get("active", True):
            continue
        try:
            kind = source.get("kind")
            if kind == "website":
                feed_url = str(source.get("feed_url") or "")
                if not feed_url:
                    feed_url = discover_feed_url(str(source.get("website_url") or ""), session=session)
                if not feed_url:
                    continue
                response = session.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=20)
                response.raise_for_status()
                items = parse_public_feed(response.content, str(source.get("name") or "Custom Source"))
            elif kind == "x":
                items = _fetch_x_items(source, session=session)
            elif kind == "telegram":
                items = _fetch_telegram_items(source, session=session)
            else:
                continue
        except Exception:
            continue
        for item in items:
            merged.setdefault(item.key, item)
    return list(merged.values())
