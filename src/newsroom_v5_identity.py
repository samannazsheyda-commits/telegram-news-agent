from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .newsroom_v5_db import transaction
from .newsroom_v5_store import NewsroomV5Store

_TRACKING_KEYS = {
    "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "ref_src",
    "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}


def canonical_source_url(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    if not parts.scheme or not parts.netloc:
        return raw
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_KEYS
    ]
    query = urlencode(query_items, doseq=True)
    result = urlunsplit((scheme, netloc, path, query, ""))
    return result[:-1] if result.endswith("/") and path == "/" else result


def story_is_tombstoned(
    store: NewsroomV5Store,
    *,
    news_key: str | None = None,
    source_item_id: str | None = None,
    source_url: str | None = None,
) -> bool:
    identity = str(source_item_id or news_key or "").strip() or None
    canonical_url = canonical_source_url(source_url) or None
    return store.is_tombstoned(news_key=identity, source_url=canonical_url)


def reject_story(store: NewsroomV5Store, story_id: str, *, actor: str = "operator") -> dict:
    story = store.get_story(story_id)
    if story is None:
        raise KeyError(story_id)
    if story.get("state") == "published":
        raise ValueError("published story cannot be rejected")
    news_key = str(story.get("source_item_id") or story.get("news_key") or "").strip() or None
    source_url = canonical_source_url(story.get("source_url")) or None
    if not news_key and not source_url:
        raise ValueError("story has no stable rejection identity")

    with transaction(store.conn):
        store.add_story_tombstone(story_id, news_key=news_key, source_url=source_url, reason="rejected_manual")
        store.conn.execute(
            "UPDATE stories SET state='rejected', updated_at=datetime('now') WHERE id=?",
            (story_id,),
        )
        store.append_audit(
            "story_rejected",
            actor=actor,
            entity_type="story",
            entity_id=story_id,
            detail={"news_key": news_key, "source_url": source_url},
        )
    return store.get_story(story_id) or {}
