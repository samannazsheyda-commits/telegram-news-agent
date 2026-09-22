from __future__ import annotations

from typing import Any, Iterable, Mapping

from .common import finalize_candidate, source_fields


def collect_x_posts(posts: Iterable[Mapping[str, Any]], source: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_id, display_name = source_fields(source)
    rows: list[dict[str, Any]] = []
    for post in posts:
        post_id = str(post.get("id") or "").strip()
        text = str(post.get("text") or "").strip()
        username = str(post.get("author_username") or source.get("identity") or "").strip().lstrip("@")
        if not post_id or not text or not username:
            continue
        media = [dict(item) for item in post.get("media") or [] if isinstance(item, Mapping) and item.get("url")]
        rows.append(
            finalize_candidate(
                {
                    "source_id": source_id,
                    "source": display_name,
                    "source_url": f"https://x.com/{username}/status/{post_id}",
                    "original_title": text,
                    "original_text": text,
                    "published_at_source": str(post.get("created_at") or ""),
                    "media_json": {"items": media},
                }
            )
        )
    return rows
