from __future__ import annotations

from typing import Any, Mapping
from xml.etree import ElementTree

from .common import clean_html, finalize_candidate, source_fields


def _text(node, *names: str) -> str:
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _link(node) -> str:
    direct = _text(node, "link")
    if direct:
        return direct
    for child in node:
        if child.tag.endswith("link") and child.attrib.get("href"):
            return str(child.attrib["href"])
    return ""


def _media(node) -> dict[str, list[dict[str, str]]]:
    items: list[dict[str, str]] = []
    for child in node.iter():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag not in {"content", "thumbnail", "enclosure"}:
            continue
        url = str(child.attrib.get("url") or "").strip()
        if not url:
            continue
        media_type = str(child.attrib.get("type") or ("image" if tag == "thumbnail" else "")).strip()
        item = {"url": url}
        if media_type:
            item["type"] = media_type
        if item not in items:
            items.append(item)
    return {"items": items}


def collect_rss(xml_text: str, source: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_id, display_name = source_fields(source)
    root = ElementTree.fromstring(xml_text)
    nodes = list(root.findall(".//item"))
    if not nodes:
        nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "entry"]
    rows: list[dict[str, Any]] = []
    for node in nodes:
        title = clean_html(_text(node, "title", "{http://www.w3.org/2005/Atom}title"))
        link = _link(node)
        if not title or not link:
            continue
        body = clean_html(
            _text(
                node,
                "description",
                "{http://www.w3.org/2005/Atom}summary",
                "{http://www.w3.org/2005/Atom}content",
            )
        )
        published = _text(
            node,
            "pubDate",
            "published",
            "updated",
            "{http://www.w3.org/2005/Atom}published",
            "{http://www.w3.org/2005/Atom}updated",
        )
        rows.append(
            finalize_candidate(
                {
                    "source_id": source_id,
                    "source": display_name,
                    "source_url": link,
                    "original_title": title,
                    "original_text": body,
                    "published_at_source": published,
                    "media_json": _media(node),
                }
            )
        )
    return rows
