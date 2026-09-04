from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .editorial_store import LocalEditorialStore, ReviewItem
from .formatters import format_news
from .services import load_state, save_state, send_telegram
from .sources import NewsItem


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_for(item: ReviewItem, title_fa: str, body_fa: str) -> str:
    news = NewsItem(
        key=item.news_key,
        source=item.source,
        title=item.original_title,
        summary=item.original_summary,
        link=item.source_url,
        published=item.published_at_source,
    )
    return format_news(news, title_fa, body_fa, marker_override="⚪️")


def _mark_seen(news_key: str, state_path: str | Path | None) -> None:
    if state_path is None:
        return
    state = load_state(state_path)
    seen = list(state.get("news_seen") or [])
    seen = [key for key in seen if key != news_key]
    seen.insert(0, news_key)
    state["news_seen"] = seen[:500]
    save_state(state, state_path)


def publish_review_item(
    store: LocalEditorialStore,
    item_id: str,
    title_fa: str,
    body_fa: str,
    token: str,
    chat_id: str,
    *,
    state_path: str | Path | None = None,
    sender=send_telegram,
) -> ReviewItem:
    item = store.get_pending(item_id)
    if item is None:
        raise ValueError("not_pending")
    title_fa = (title_fa or "").strip()
    body_fa = (body_fa or "").strip()
    if not title_fa:
        raise ValueError("headline_required")
    if not item.source or not item.source_url:
        raise ValueError("source_required")
    message = _message_for(item, title_fa, body_fa)
    if not message:
        raise ValueError("invalid_message")

    # Telegram confirmation comes first. Never mutate editorial state before it succeeds.
    sender(message, token, chat_id)
    _mark_seen(item.news_key, state_path)
    return store.move_to_history(
        item.id,
        status="published_manual",
        final_persian_title=title_fa,
        final_persian_body=body_fa,
        decision_at=_now(),
    )


def reject_review_item(store: LocalEditorialStore, item_id: str) -> ReviewItem:
    item = store.get_pending(item_id)
    if item is None:
        raise ValueError("not_pending")
    return store.move_to_history(item.id, status="rejected_manual", decision_at=_now())
