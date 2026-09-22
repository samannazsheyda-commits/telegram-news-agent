from __future__ import annotations

from typing import Any, Mapping

from .common import finalize_candidate, source_fields


def collect_manual(payload: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    source_id, display_name = source_fields(source)
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not title:
        raise ValueError("manual story title is required")
    return finalize_candidate(
        {
            "source_id": source_id,
            "source": display_name,
            "source_url": str(payload.get("url") or ""),
            "original_title": title,
            "original_text": body,
            "published_at_source": str(payload.get("published_at") or ""),
            "media_json": {"items": list(payload.get("media") or [])},
        }
    )
