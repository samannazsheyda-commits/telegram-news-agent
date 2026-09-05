from __future__ import annotations

import requests

from .sources import NewsItem, _fetch_google_news_query


_BUILTIN_X_NEWSROOMS = (
    ("Reuters", "@Reuters"),
    ("Associated Press", "@AP"),
    ("AFP", "@AFP"),
    ("BBC World", "@BBCWorld"),
    ("CNN", "@CNN"),
    ("France 24", "@FRANCE24"),
    ("Al Jazeera English", "@AJEnglish"),
    ("Al Arabiya English", "@AlArabiya_Eng"),
    ("Times of Israel", "@TimesofIsrael"),
    ("Haaretz", "@haaretzcom"),
    ("Axios", "@axios"),
)

_X_IRAN_QUERY = (
    "(Iran OR Iranian OR Tehran OR IRGC OR Quds OR Hormuz OR missile OR drone OR nuclear "
    "OR Israel OR Lebanon OR Hezbollah OR sanctions OR airspace OR NOTAM)"
)


def builtin_x_news_sources() -> tuple[dict[str, str], ...]:
    return tuple({"name": name, "handle": handle} for name, handle in _BUILTIN_X_NEWSROOMS)


def _default_searcher(source: dict[str, str], session=requests) -> list[NewsItem]:
    handle = source["handle"].lstrip("@")
    label = f'{source["name"]} / X'
    query = f'{_X_IRAN_QUERY} site:x.com/{handle}'
    return _fetch_google_news_query(session, label, query, "en", allow_special_source=True)


def fetch_builtin_x_news_items(*, searcher=None, session=requests) -> list[NewsItem]:
    """Best-effort monitoring of official newsroom posts indexed from X.

    X posts are treated as fast editorial signals. They still pass the agent's
    normal freshness, Iran relevance, deduplication and translation gates.
    """
    merged: dict[str, NewsItem] = {}
    for source in builtin_x_news_sources():
        try:
            items = searcher(source) if searcher else _default_searcher(source, session=session)
        except Exception:
            continue
        for item in items[:20]:
            display = f'{source["name"]} / X'
            normalized = item if item.source.endswith(" / X") else NewsItem(
                item.key, display, item.title, item.summary, item.link, item.published
            )
            merged.setdefault(normalized.key, normalized)
    return list(merged.values())
