from __future__ import annotations

import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from .collectors.rss import collect_rss
from .collectors.telegram import collect_telegram_messages
from .collectors.website import collect_website
from .collectors.x import collect_x_posts


class SourceFetcher:
    def __init__(
        self,
        *,
        session: Any | None = None,
        x_bearer_token: str | None = None,
        timeout_seconds: float = 20,
    ) -> None:
        self.session = session or requests.Session()
        self.x_bearer_token = str(x_bearer_token or "").strip()
        self.timeout_seconds = max(3.0, float(timeout_seconds))
        self.headers = {"User-Agent": "Bikhabar-Vision5/1.0 (+news collector)"}

    def fetch(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        kind = str(source.get("kind") or "").strip().lower()
        identity = str(source.get("identity") or "").strip()
        if not identity:
            raise ValueError("source identity is required")
        if kind == "rss":
            response = self.session.get(identity, headers=self.headers, timeout=self.timeout_seconds)
            response.raise_for_status()
            return collect_rss(response.text, source)
        if kind == "website":
            response = self.session.get(identity, headers=self.headers, timeout=self.timeout_seconds)
            response.raise_for_status()
            return [collect_website(response.text, identity, source)]
        if kind == "telegram":
            return self._telegram(identity, source)
        if kind == "x":
            return self._x(identity, source)
        if kind == "manual":
            return []
        raise ValueError(f"unsupported source kind: {kind}")

    def _telegram(self, identity: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        channel = identity.lstrip("@").strip("/")
        response = self.session.get(
            f"https://t.me/s/{channel}",
            headers=self.headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        messages: list[dict[str, Any]] = []
        for node in soup.select(".tgme_widget_message[data-post]"):
            post = str(node.get("data-post") or "")
            message_id = post.rsplit("/", 1)[-1]
            text_node = node.select_one(".tgme_widget_message_text")
            text = text_node.get_text("\n", strip=True) if text_node else ""
            time_node = node.select_one("time[datetime]")
            photo_node = node.select_one(".tgme_widget_message_photo_wrap")
            media = None
            if photo_node:
                style = str(photo_node.get("style") or "")
                match = re.search(r"url\(['\"]?([^'\")]+)", style)
                if match:
                    media = {"type": "photo", "url": match.group(1)}
            messages.append(
                {
                    "message_id": message_id,
                    "text": text,
                    "date": str(time_node.get("datetime") or "") if time_node else "",
                    "chat": {"username": channel},
                    "media": media,
                }
            )
        return collect_telegram_messages(messages, source)

    def _x(self, identity: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.x_bearer_token:
            raise RuntimeError("X_BEARER_TOKEN is required for X sources")
        username = identity.lstrip("@")
        response = self.session.get(
            "https://api.x.com/2/tweets/search/recent",
            headers={"Authorization": f"Bearer {self.x_bearer_token}"},
            params={
                "query": f"from:{username} -is:retweet",
                "max_results": 20,
                "tweet.fields": "created_at,author_id,attachments",
                "expansions": "author_id,attachments.media_keys",
                "media.fields": "url,preview_image_url,type",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json() or {}
        includes = payload.get("includes") or {}
        users = {str(row.get("id")): row for row in includes.get("users") or []}
        media = {str(row.get("media_key")): row for row in includes.get("media") or []}
        posts: list[dict[str, Any]] = []
        for row in payload.get("data") or []:
            author = users.get(str(row.get("author_id"))) or {}
            attachments = row.get("attachments") or {}
            post_media = []
            for key in attachments.get("media_keys") or []:
                item = media.get(str(key)) or {}
                url = item.get("url") or item.get("preview_image_url")
                if url:
                    post_media.append({"type": item.get("type") or "media", "url": url})
            posts.append(
                {
                    "id": row.get("id"),
                    "text": row.get("text"),
                    "created_at": row.get("created_at"),
                    "author_username": author.get("username") or username,
                    "media": post_media,
                }
            )
        return collect_x_posts(posts, source)


class CollectorRuntime:
    def __init__(self, *, store: Any, queue: Any, fetcher: SourceFetcher) -> None:
        self.store = store
        self.queue = queue
        self.fetcher = fetcher

    def run_once(self) -> dict[str, int]:
        totals = {"sources": 0, "received": 0, "inserted": 0, "duplicates": 0, "failed": 0}
        for source in self.store.list_sources():
            if not bool(source.get("enabled")):
                continue
            totals["sources"] += 1
            received = inserted = 0
            try:
                candidates = self.fetcher.fetch(source)
                received = len(candidates)
                for candidate in candidates:
                    story, was_inserted = self.store.ingest_story(candidate)
                    if was_inserted:
                        inserted += 1
                        self.queue.enqueue("translate", {"story_id": str(story["id"])})
                totals["received"] += received
                totals["inserted"] += inserted
                totals["duplicates"] += received - inserted
                self.store.record_collector_run(
                    str(source["id"]),
                    status="succeeded",
                    received=received,
                    inserted=inserted,
                )
            except Exception as exc:
                totals["failed"] += 1
                self.store.record_collector_run(
                    str(source["id"]),
                    status="failed",
                    received=received,
                    inserted=inserted,
                    error=str(exc),
                )
        return totals
