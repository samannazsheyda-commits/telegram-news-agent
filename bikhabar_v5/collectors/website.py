from __future__ import annotations

from typing import Any, Mapping

from bs4 import BeautifulSoup

from .common import finalize_candidate, source_fields


def _meta(soup: BeautifulSoup, key: str) -> str:
    node = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
    return str(node.get("content") or "").strip() if node else ""


def collect_website(html: str, source_url: str, source: Mapping[str, Any]) -> dict[str, Any]:
    source_id, display_name = source_fields(source)
    soup = BeautifulSoup(html, "html.parser")
    title = _meta(soup, "og:title") or (soup.title.get_text(" ", strip=True) if soup.title else "")
    article = soup.find("article") or soup.find("main") or soup.body
    paragraphs = [" ".join(node.get_text(" ", strip=True).split()) for node in article.find_all("p")] if article else []
    body = "\n\n".join(item for item in paragraphs if item)
    image = _meta(soup, "og:image")
    return finalize_candidate(
        {
            "source_id": source_id,
            "source": display_name,
            "source_url": source_url,
            "original_title": title,
            "original_text": body,
            "published_at_source": _meta(soup, "article:published_time"),
            "media_json": {"items": ([{"url": image, "type": "image"}] if image else [])},
        }
    )
