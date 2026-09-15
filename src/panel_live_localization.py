from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .formatters import format_news
from .sources import NewsItem


def has_persian(value: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in str(value or ""))


def raw_fields(row: dict[str, Any]) -> tuple[str, str]:
    title = str(row.get("original_title") or row.get("title") or "").strip()
    body = str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip()
    return title, body


def build_final_message(row: dict[str, Any], title_fa: str, body_fa: str) -> str:
    persisted = str(row.get("final_message") or row.get("telegram_message") or "").strip()
    if persisted:
        return persisted
    item = NewsItem(
        key=str(row.get("news_key") or row.get("item_id") or row.get("id") or ""),
        source=str(row.get("source") or ""),
        title=str(row.get("original_title") or row.get("title") or ""),
        summary=str(row.get("original_summary") or row.get("summary") or row.get("body") or ""),
        link=str(row.get("source_url") or row.get("link") or ""),
        published=str(row.get("published_at_source") or row.get("published") or ""),
    )
    return str(format_news(item, title_fa, body_fa, marker_override=None) or "").strip()


def localize_live_row(
    row: dict[str, Any],
    *,
    translator: Callable[[str], str],
    localized_at: str,
) -> tuple[dict[str, Any], bool]:
    current = dict(row)
    persisted_title = str(
        current.get("final_persian_title")
        or current.get("persian_title")
        or current.get("display_title")
        or ""
    ).strip()
    persisted_body = str(current.get("final_persian_body") or current.get("persian_body") or "").strip()
    persisted_final = str(current.get("final_message") or current.get("telegram_message") or "").strip()

    if has_persian(persisted_title) and persisted_final:
        return current, False

    raw_title, raw_body = raw_fields(current)
    if not raw_title and not has_persian(persisted_title):
        raise RuntimeError("live_localization_missing_title")

    if has_persian(persisted_title):
        title_fa = persisted_title
    elif has_persian(raw_title):
        title_fa = raw_title
    else:
        title_fa = str(translator(raw_title) or "").strip()

    if not has_persian(title_fa):
        raise RuntimeError("live_localization_failed")

    if persisted_body:
        body_fa = persisted_body
    elif not raw_body:
        body_fa = ""
    elif has_persian(raw_body):
        body_fa = raw_body
    else:
        body_fa = str(translator(raw_body) or "").strip()
        if body_fa and not has_persian(body_fa):
            body_fa = ""

    final_message = persisted_final or build_final_message(current, title_fa, body_fa)
    if not final_message:
        raise RuntimeError("live_localization_format_failed")

    current.update(
        persian_title=title_fa,
        persian_body=body_fa,
        final_message=final_message,
        localized_at=localized_at,
    )
    return current, True
