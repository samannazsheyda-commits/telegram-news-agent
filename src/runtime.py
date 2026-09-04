from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from . import main as agent
from .custom_sources import fetch_custom_news_items
from .editorial_store import LocalEditorialStore, ReviewItem


_store = LocalEditorialStore()
_original_fetch_news_items = agent.fetch_news_items
_original_audit_news = agent._audit_news
_original_format_news = agent.format_news
_original_send_telegram = agent.send_telegram
_pending_auto_key: str | None = None


def _combined_fetch_news_items():
    merged = {item.key: item for item in _original_fetch_news_items()}
    try:
        custom = fetch_custom_news_items()
    except Exception as exc:
        print(f"Custom source error: {exc}", file=sys.stderr)
        custom = []
    for item in custom:
        merged.setdefault(item.key, item)
    return list(merged.values())


def _review_record(item, reason: str, now: datetime) -> ReviewItem:
    title_fa = ""
    body_fa = ""
    try:
        title_fa = agent.translate_to_fa(item.title)
    except Exception:
        title_fa = ""
    try:
        detail = agent.fetch_news_detail(item)
        body_fa = agent.translate_to_fa(detail[:1200]) if detail else ""
    except Exception:
        body_fa = ""
    return ReviewItem.for_news(
        news_key=item.key,
        source=item.source,
        source_url=item.link,
        original_title=item.title,
        original_summary=item.summary,
        persian_title=title_fa,
        persian_body=body_fa,
        published_at_source=item.published,
        discovered_at=now.astimezone(timezone.utc).isoformat(),
        rejection_reason=reason,
    )


def _audit_with_editorial_store(state: dict, item, reason: str, now: datetime) -> None:
    _original_audit_news(state, item, reason, now)
    try:
        existing = _store.find_by_news_key(item.key)
        if existing and existing.status in {"published_manual", "published_auto", "rejected_manual"}:
            return
        record = _review_record(item, reason, now)
        if reason in {"invalid_publish_time", "not_today_tehran"}:
            _store.upsert_history(
                ReviewItem.for_news(
                    news_key=record.news_key,
                    source=record.source,
                    source_url=record.source_url,
                    original_title=record.original_title,
                    original_summary=record.original_summary,
                    persian_title=record.persian_title,
                    persian_body=record.persian_body,
                    published_at_source=record.published_at_source,
                    discovered_at=record.discovered_at,
                    rejection_reason=record.rejection_reason,
                    status="superseded",
                )
            )
        else:
            _store.upsert_queue(record)
    except Exception as exc:
        print(f"Editorial queue error: {exc}", file=sys.stderr)


def _format_with_tracking(item, title_fa: str, summary_fa: str, marker_override: str | None = None) -> str:
    global _pending_auto_key
    message = _original_format_news(item, title_fa, summary_fa, marker_override=marker_override)
    _pending_auto_key = item.key if message else None
    return message


def _send_with_tracking(text: str, bot_token: str, chat_id: str, *args, **kwargs) -> None:
    global _pending_auto_key
    key = _pending_auto_key
    _original_send_telegram(text, bot_token, chat_id, *args, **kwargs)
    if key:
        try:
            _store.mark_auto_published(key)
        except Exception as exc:
            print(f"Editorial auto transition error: {exc}", file=sys.stderr)
        finally:
            _pending_auto_key = None


def install_integrations() -> None:
    agent.fetch_news_items = _combined_fetch_news_items
    agent._audit_news = _audit_with_editorial_store
    agent.format_news = _format_with_tracking
    agent.send_telegram = _send_with_tracking


def run() -> int:
    install_integrations()
    return agent.run()


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_integrations()
    return agent.monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
