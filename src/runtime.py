from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from . import formatters as news_formatters
from . import main as agent
from .custom_sources import fetch_custom_news_items
from .editorial_rules import (
    editorial_detail,
    fetch_priority_news_items,
    is_duplicate_story,
    is_low_value_company_news,
    is_priority_security_news,
)
from .editorial_store import LocalEditorialStore, ReviewItem
from .hormuz import fetch_hormuz_traffic_report, format_hormuz_report, hormuz_report_due
from .sources import NewsItem


_store = LocalEditorialStore()
_original_fetch_news_items = agent.fetch_news_items
_original_audit_news = agent._audit_news
_original_format_news = agent.format_news
_original_send_telegram = agent.send_telegram
_original_news_rejection_reason = agent._news_rejection_reason
_original_event_priority = agent._event_priority
_pending_auto_key: str | None = None
_pending_auto_item: NewsItem | None = None
_sent_news_items: list[NewsItem] = []
_priority_news_keys: set[str] = set()
RECENT_DEDUP_WINDOW = timedelta(hours=72)
RECENT_DEDUP_LIMIT = 300
PRIORITY_LOOKBACK = timedelta(hours=72)


def _terminal_manual_keys() -> set[str]:
    try:
        return {
            str(record.get("news_key") or "")
            for record in _store.history()
            if record.get("status") in {"published_manual", "published_auto"}
        }
    except Exception:
        return set()


def _record_to_item(record: dict) -> NewsItem | None:
    try:
        return NewsItem(
            str(record.get("key") or ""),
            str(record.get("source") or ""),
            str(record.get("title") or ""),
            str(record.get("summary") or ""),
            str(record.get("link") or ""),
            str(record.get("published") or ""),
        )
    except Exception:
        return None


def _recent_published_items(now: datetime | None = None) -> list[NewsItem]:
    now = now or datetime.now(timezone.utc)
    try:
        state = agent.load_state(agent.STATE_PATH)
    except Exception:
        return []
    result: list[NewsItem] = []
    for record in state.get("recent_published_news") or []:
        sent_at_raw = str(record.get("sent_at") or "")
        try:
            sent_at = datetime.fromisoformat(sent_at_raw.replace("Z", "+00:00"))
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=timezone.utc)
            sent_at = sent_at.astimezone(timezone.utc)
        except ValueError:
            sent_at = now
        if now - sent_at > RECENT_DEDUP_WINDOW:
            continue
        item = _record_to_item(record)
        if item and item.title:
            result.append(item)
    return result


def _is_recent_duplicate(item: NewsItem, references: list[NewsItem]) -> bool:
    return any(is_duplicate_story(item, previous) for previous in references)


def _combined_fetch_news_items():
    global _priority_news_keys
    terminal = _terminal_manual_keys()
    merged: dict[str, NewsItem] = {}

    for item in _original_fetch_news_items():
        if item.key in terminal:
            continue
        if is_low_value_company_news(item):
            print(f"NEWS_SUPPRESSED low_value_company source={item.source!r} title={item.title!r}")
            continue
        merged.setdefault(item.key, item)

    try:
        custom = fetch_custom_news_items()
    except Exception as exc:
        print(f"Custom source error: {exc}", file=sys.stderr)
        custom = []
    for item in custom:
        if item.key in terminal:
            continue
        if is_low_value_company_news(item):
            print(f"NEWS_SUPPRESSED low_value_company source={item.source!r} title={item.title!r}")
            continue
        merged.setdefault(item.key, item)

    try:
        priority_items = fetch_priority_news_items()
    except Exception as exc:
        print(f"Priority source error: {exc}", file=sys.stderr)
        priority_items = []
    _priority_news_keys = {item.key for item in priority_items}
    for item in priority_items:
        if item.key in terminal:
            continue
        if is_low_value_company_news(item):
            continue
        merged.setdefault(item.key, item)

    recent = _recent_published_items()
    filtered: list[NewsItem] = []
    for item in merged.values():
        references = recent + filtered
        if _is_recent_duplicate(item, references):
            print(f"NEWS_SUPPRESSED duplicate_event source={item.source!r} title={item.title!r}")
            continue
        filtered.append(item)
    return filtered


def _priority_rejection_reason(item: NewsItem, now: datetime) -> str | None:
    reason = _original_news_rejection_reason(item, now)
    if reason != "not_today_tehran":
        return reason
    if item.key not in _priority_news_keys and not is_priority_security_news(item):
        return reason
    published = agent._published_dt(item.published)
    if not published:
        return reason
    age = now.astimezone(timezone.utc) - published
    if age < timedelta(0) or age > PRIORITY_LOOKBACK:
        return reason
    current_item = NewsItem(
        item.key,
        item.source,
        item.title,
        item.summary,
        item.link,
        format_datetime(now.astimezone(timezone.utc)),
    )
    return _original_news_rejection_reason(current_item, now)


def _priority_event_priority(item: NewsItem) -> int:
    base = _original_event_priority(item)
    if item.key in _priority_news_keys or is_priority_security_news(item):
        return max(base, 95)
    return base


def _review_record(item, reason: str, now: datetime) -> ReviewItem:
    title_fa = ""
    body_fa = ""
    if reason not in {"invalid_publish_time", "not_today_tehran"}:
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
    global _pending_auto_key, _pending_auto_item
    message = _original_format_news(item, title_fa, summary_fa, marker_override=marker_override)
    _pending_auto_key = item.key if message else None
    _pending_auto_item = item if message else None
    return message


def _send_with_tracking(text: str, bot_token: str, chat_id: str, *args, **kwargs) -> None:
    global _pending_auto_key, _pending_auto_item
    key = _pending_auto_key
    item = _pending_auto_item
    try:
        _original_send_telegram(text, bot_token, chat_id, *args, **kwargs)
    except Exception:
        _pending_auto_key = None
        _pending_auto_item = None
        raise
    if key:
        try:
            _store.mark_auto_published(key)
        except Exception as exc:
            print(f"Editorial auto transition error: {exc}", file=sys.stderr)
        if item is not None:
            _sent_news_items.append(item)
        _pending_auto_key = None
        _pending_auto_item = None


def _flush_recent_published(now: datetime | None = None) -> None:
    if not _sent_news_items:
        return
    now = now or datetime.now(timezone.utc)
    try:
        state = agent.load_state(agent.STATE_PATH)
        existing = list(state.get("recent_published_news") or [])
        fresh_existing = []
        for record in existing:
            sent_at_raw = str(record.get("sent_at") or "")
            try:
                sent_at = datetime.fromisoformat(sent_at_raw.replace("Z", "+00:00"))
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=timezone.utc)
                sent_at = sent_at.astimezone(timezone.utc)
            except ValueError:
                sent_at = now
            if now - sent_at <= RECENT_DEDUP_WINDOW:
                fresh_existing.append(record)

        new_records = [
            {
                "key": item.key,
                "source": item.source,
                "title": item.title,
                "summary": item.summary,
                "link": item.link,
                "published": item.published,
                "sent_at": now.isoformat(),
            }
            for item in _sent_news_items
        ]
        state["recent_published_news"] = (new_records + fresh_existing)[:RECENT_DEDUP_LIMIT]
        agent.save_state(state, agent.STATE_PATH)
        _sent_news_items.clear()
    except Exception as exc:
        print(f"Recent dedup persistence error: {exc}", file=sys.stderr)


def _send_hormuz_daily(now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    state = agent.load_state(agent.STATE_PATH)
    if not hormuz_report_due(state, now):
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return

    local = now.astimezone(agent.TEHRAN)
    report_date = local.date() - timedelta(days=1)
    report = fetch_hormuz_traffic_report(report_date)

    # No verified observed vessel count = no channel post. Keep the day unsent so
    # later monitor cycles can retry if Kpler/Vortexa/Reuters publish a real count.
    if report.observed_count is None:
        print(f"HORMUZ_SKIPPED no_verified_count report_date={report_date.isoformat()}")
        return

    translated_details: list[str] = []
    for detail in report.vessel_details:
        try:
            translated = agent.translate_to_fa(detail)
        except Exception:
            translated = ""
        translated_details.append(translated or detail)
    if translated_details:
        report = replace(report, vessel_details=tuple(translated_details))

    agent.send_telegram(format_hormuz_report(report), token, chat_id)
    state["hormuz_last_sent_date"] = local.date().isoformat()
    agent.save_state(state, agent.STATE_PATH)


def install_integrations() -> None:
    agent.fetch_news_items = _combined_fetch_news_items
    agent._audit_news = _audit_with_editorial_store
    agent._same_story = is_duplicate_story
    agent._news_rejection_reason = _priority_rejection_reason
    agent._event_priority = _priority_event_priority
    news_formatters._up_to_two_sentences = editorial_detail
    agent.format_news = _format_with_tracking
    agent.send_telegram = _send_with_tracking


def run(now: datetime | None = None) -> int:
    install_integrations()
    rc = agent.run(now)
    if rc == 0:
        try:
            _send_hormuz_daily(now)
        except Exception as exc:
            print(f"Hormuz daily report error: {exc}", file=sys.stderr)
    _flush_recent_published(now)
    return rc


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
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
