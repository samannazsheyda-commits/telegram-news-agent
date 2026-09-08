from __future__ import annotations

import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from .newsroom_models import RawNewsItem
from .sources import USER_AGENT


TRUMP_ACCOUNT_ID = "107780257626128497"
TRUTH_API = f"https://truthsocial.com/api/v1/accounts/{TRUMP_ACCOUNT_ID}/statuses"
_RELEVANCE_TERMS = (
    "iran",
    "iranian",
    "tehran",
    "hormuz",
    "oil",
    "crude",
    "petroleum",
    "ایران",
    "تهران",
    "هرمز",
    "نفت",
)


def _plain_html(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def _attachment_text(status: dict) -> str:
    parts: list[str] = []
    for attachment in status.get("media_attachments") or []:
        if not isinstance(attachment, dict):
            continue
        description = re.sub(r"\s+", " ", str(attachment.get("description") or "")).strip()
        if description:
            parts.append(description)
    return " ".join(parts)


def _media_urls(status: dict) -> list[str]:
    result: list[str] = []
    for attachment in status.get("media_attachments") or []:
        if not isinstance(attachment, dict):
            continue
        url = str(attachment.get("url") or attachment.get("remote_url") or attachment.get("preview_url") or "").strip()
        if url and url not in result:
            result.append(url)
    return result


def _relevance_text(status: dict) -> str:
    parts = [_plain_html(str(status.get("content") or "")), _attachment_text(status)]
    reblog = status.get("reblog")
    if isinstance(reblog, dict):
        parts.extend([_plain_html(str(reblog.get("content") or "")), _attachment_text(reblog)])
    return re.sub(r"\s+", " ", " ".join(part for part in parts if part)).strip()


def _is_relevant(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _RELEVANCE_TERMS)


def parse_truth_status(status: dict, *, fetched_at: str | None = None) -> RawNewsItem | None:
    post_id = str(status.get("id") or "").strip()
    if not post_id:
        return None

    relevance = _relevance_text(status)
    if not relevance or not _is_relevant(relevance):
        return None

    content = _plain_html(str(status.get("content") or ""))
    attachment_text = _attachment_text(status)
    title = content or attachment_text or relevance
    summary_parts = [part for part in (content, attachment_text) if part]
    summary = " ".join(dict.fromkeys(summary_parts))

    source_url = str(status.get("url") or "").strip()
    if not source_url:
        source_url = f"https://truthsocial.com/@realDonaldTrump/{post_id}"

    created_at = str(status.get("created_at") or "").strip()
    resolved_fetched_at = fetched_at
    if not resolved_fetched_at:
        resolved_fetched_at = datetime.now(timezone.utc).isoformat()

    media = _media_urls(status)
    reblog = status.get("reblog")
    if isinstance(reblog, dict):
        for url in _media_urls(reblog):
            if url not in media:
                media.append(url)

    return RawNewsItem(
        source="Truth Social",
        source_url=source_url,
        source_item_id=post_id,
        published_at=created_at,
        fetched_at=resolved_fetched_at,
        title=title,
        summary=summary,
        media=media,
        source_priority="protected",
    )


def fetch_trump_truth_items(session=requests, limit: int = 40) -> list[RawNewsItem]:
    response = session.get(
        TRUTH_API,
        params={"exclude_replies": "true", "with_muted": "true", "limit": max(1, min(40, int(limit)))},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []
    fetched_at = datetime.now(timezone.utc).isoformat()
    result: list[RawNewsItem] = []
    for status in payload:
        if not isinstance(status, dict):
            continue
        item = parse_truth_status(status, fetched_at=fetched_at)
        if item is not None:
            result.append(item)
    return result
