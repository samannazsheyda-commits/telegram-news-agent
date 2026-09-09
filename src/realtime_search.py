from __future__ import annotations

import requests

from .managed_sources import _system_active, source_overrides, system_source_definitions
from .sources import NewsItem, _fetch_google_news_query, is_regional_security_alert, is_security_alert


def _fresh_query(query: str) -> str:
    text = str(query or "").strip()
    return text if "when:" in text.lower() else f"{text} when:1h"


def _fetch_group(group: str, session=requests) -> list[NewsItem]:
    overrides = source_overrides()
    merged: dict[str, NewsItem] = {}
    rows = [
        row for row in system_source_definitions()
        if row.get("kind") == "system_query" and row.get("group") == group
    ]
    for row in rows:
        source_id = str(row["id"])
        if not _system_active(source_id, overrides):
            continue
        source_name = str(row["name"])
        query = _fresh_query(str(row["query"]))
        lang = str(row["lang"])
        try:
            items = _fetch_google_news_query(
                session,
                source_name,
                query,
                lang,
                allow_special_source=(group == "special"),
            )
        except Exception:
            continue
        for item in items[:12]:
            combined = f"{item.title} {item.summary}"
            if source_name in {"TankerTrackers", "NOTAM / Airspace"} and not is_security_alert(combined):
                continue
            if source_name == "Al Arabiya" and not is_regional_security_alert(combined):
                continue
            merged.setdefault(item.key, item)
    return list(merged.values())


def fetch_fresh_base_news_items(session=requests) -> list[NewsItem]:
    merged: dict[str, NewsItem] = {}
    for group in ("news", "special"):
        for item in _fetch_group(group, session=session):
            merged.setdefault(item.key, item)
    return list(merged.values())


def fetch_fresh_priority_news_items(session=requests) -> list[NewsItem]:
    return _fetch_group("priority", session=session)
