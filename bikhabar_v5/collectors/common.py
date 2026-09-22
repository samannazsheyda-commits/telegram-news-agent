from __future__ import annotations

import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping

from bs4 import BeautifulSoup

from ..identity import ensure_story_identity


def clean_html(value: str | None) -> str:
    soup = BeautifulSoup(str(value or ""), "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split())


def iso_timestamp(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = parsedate_to_datetime(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def source_fields(source: Mapping[str, Any]) -> tuple[str, str]:
    source_id = str(source.get("id") or "").strip()
    display_name = str(source.get("display_name") or source.get("name") or "").strip()
    if not source_id or not display_name:
        raise ValueError("collector source requires id and display_name")
    return source_id, display_name


def finalize_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    prepared = ensure_story_identity(candidate)
    prepared["id"] = str(prepared.get("id") or uuid.uuid5(uuid.NAMESPACE_URL, prepared["fingerprint"]))
    prepared["published_at_source"] = iso_timestamp(str(prepared.get("published_at_source") or ""))
    prepared["media_json"] = dict(prepared.get("media_json") or {"items": []})
    return prepared
