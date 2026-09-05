from __future__ import annotations

from difflib import SequenceMatcher

import requests
from bs4 import BeautifulSoup

from .sources import NewsItem, USER_AGENT, _clean_detail, _detail_is_boilerplate, _detail_is_useful, _story_title


MAX_DETAIL_CHARS = 1800
MAX_BODY_PARAGRAPHS = 12
MAX_SELECTED_SEGMENTS = 4


def _is_redundant(candidate: str, selected: list[str]) -> bool:
    normalized = _story_title(candidate)
    if not normalized:
        return True
    for existing in selected:
        other = _story_title(existing)
        if not other:
            continue
        if normalized in other or other in normalized:
            return True
        if SequenceMatcher(None, normalized, other).ratio() >= 0.76:
            return True
    return False


def _add_candidate(title: str, candidate: str, selected: list[str]) -> None:
    detail = _clean_detail(candidate)
    if not _detail_is_useful(title, detail):
        return
    if _detail_is_boilerplate(detail) or _is_redundant(detail, selected):
        return
    selected.append(detail)


def fetch_news_detail_enriched(item: NewsItem, session=requests) -> str:
    """Return enough source-backed context to make an incomplete headline understandable.

    The source-written deck/subheadline is kept first, then non-redundant lead/body
    facts are added when available. Output length follows the information in the
    source rather than a fixed sentence count. Nothing is invented.
    """
    summary = _clean_detail(item.summary)
    selected: list[str] = []

    if item.link:
        try:
            response = session.get(
                item.link,
                headers={"User-Agent": USER_AGENT},
                timeout=12,
                allow_redirects=True,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            for attrs in (
                {"property": "og:description"},
                {"name": "description"},
                {"name": "twitter:description"},
            ):
                node = soup.find("meta", attrs=attrs)
                if node and node.get("content"):
                    _add_candidate(item.title, str(node.get("content")), selected)

            for paragraph in soup.find_all("p")[:MAX_BODY_PARAGRAPHS]:
                _add_candidate(item.title, paragraph.get_text(" ", strip=True), selected)
                if len(selected) >= MAX_SELECTED_SEGMENTS:
                    break
        except Exception:
            selected = []

    if not selected:
        _add_candidate(item.title, summary, selected)
    elif summary and not _is_redundant(summary, selected):
        # RSS summaries can occasionally contain a useful fact that is absent from
        # the page metadata, but they remain lower priority than source-written text.
        _add_candidate(item.title, summary, selected)

    if not selected:
        return ""

    result = " ".join(selected)
    if len(result) <= MAX_DETAIL_CHARS:
        return result
    return result[:MAX_DETAIL_CHARS].rsplit(" ", 1)[0].strip() + "…"
