from __future__ import annotations

import os

from .newsroom_store_factory import create_runtime_store
from .newsroom_v5_pipeline import shadow_ingest


def _enabled() -> bool:
    return str(os.environ.get("NEWSROOM_V5_SHADOW_PIPELINE", "false") or "false").strip().lower() in {"1", "true", "yes", "on"}


def _record(item) -> dict:
    return {
        "id": str(getattr(item, "source_item_id", "") or "").strip() or None,
        "news_key": str(getattr(item, "source_item_id", "") or "").strip() or None,
        "source_id": str(getattr(item, "source", "") or "").strip() or None,
        "source_name": str(getattr(item, "source", "") or "").strip() or None,
        "source_url": str(getattr(item, "source_url", "") or "").strip() or None,
        "source_item_id": str(getattr(item, "source_item_id", "") or "").strip() or None,
        "original_title": str(getattr(item, "title", "") or "").strip(),
        "original_body": str(getattr(item, "summary", "") or "").strip(),
        "published_at_source": str(getattr(item, "published_at", "") or "").strip() or None,
        "discovered_at": str(getattr(item, "fetched_at", "") or "").strip() or None,
    }


def run_v5_shadow_items(items, *, store=None) -> dict:
    if not _enabled():
        return {"enabled": False, "ingested": 0, "suppressed": 0, "published": 0}
    own_store = False
    if store is None:
        store = create_runtime_store()
        own_store = store is not None
    if store is None:
        return {"enabled": True, "ingested": 0, "suppressed": 0, "published": 0, "error": "sqlite_store_not_enabled"}
    try:
        result = shadow_ingest([_record(item) for item in items], store)
        result["enabled"] = True
        # Shadow adapter has no sender and cannot create a publication.
        result["published"] = 0
        return result
    finally:
        if own_store:
            store.close()
