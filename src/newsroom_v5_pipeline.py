from __future__ import annotations

import hashlib
from typing import Any, Callable

from .newsroom_v5_editorial import route_editorial
from .newsroom_v5_identity import canonical_source_url, reject_story, story_is_tombstoned
from .newsroom_v5_jobs import enqueue_once
from .newsroom_v5_store import NewsroomV5Store
from .newsroom_v5_translation import translate_story
from .services import translate_to_fa


def _story_id(record: dict) -> str:
    direct = str(record.get("id") or record.get("news_key") or record.get("source_item_id") or "").strip()
    if direct:
        return direct
    url = canonical_source_url(record.get("source_url"))
    if url:
        return "url-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    material = "\x1f".join(str(record.get(key) or "") for key in ("source_id", "original_title", "published_at_source"))
    return "story-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


class NewsroomV5Pipeline:
    def __init__(
        self,
        store: NewsroomV5Store,
        *,
        lightweight_translator: Callable[[str], str] = translate_to_fa,
        ai_translator: Callable[[str], Any] | None = None,
        auto_publish_enabled: bool | None = None,
    ) -> None:
        self.store = store
        self.lightweight_translator = lightweight_translator
        self.ai_translator = ai_translator
        self.auto_publish_enabled = auto_publish_enabled

    def ingest(self, record: dict) -> dict:
        story_id = _story_id(record)
        news_key = str(record.get("source_item_id") or record.get("news_key") or "").strip() or None
        source_url = canonical_source_url(record.get("source_url")) or None

        if story_is_tombstoned(self.store, news_key=news_key, source_url=source_url):
            self.store.append_audit(
                "story_suppressed_tombstone",
                entity_type="story",
                entity_id=story_id,
                detail={"news_key": news_key, "source_url": source_url},
            )
            return {"id": story_id, "state": "rejected", "suppressed": True}

        existing = self.store.find_story(news_key=news_key, source_url=source_url)
        if existing is not None:
            if existing.get("state") == "rejected":
                return {"id": existing["id"], "state": "rejected", "suppressed": True}
            return {"id": existing["id"], "state": existing["state"], "suppressed": False, "existing": True}

        story = dict(record)
        story.update(
            id=story_id,
            news_key=news_key,
            source_item_id=str(record.get("source_item_id") or news_key or "").strip() or None,
            source_url=source_url or str(record.get("source_url") or "").strip() or None,
            state="received",
        )
        stored = self.store.upsert_story(story)
        enqueue_once(self.store, "translate_story", story_id=story_id, payload={"story_id": story_id})
        self.store.append_audit("story_ingested", entity_type="story", entity_id=story_id)
        return {"id": story_id, "state": stored["state"], "suppressed": False}

    def process_translation(self, story_id: str) -> dict:
        result = translate_story(
            self.store,
            story_id,
            lightweight=self.lightweight_translator,
            ai_fallback=self.ai_translator,
        )
        if result["status"] == "translated":
            enqueue_once(self.store, "editorial_story", story_id=story_id, payload={"story_id": story_id})
        return result

    def process_editorial(
        self,
        story_id: str,
        decision: Any,
        *,
        source_enabled: bool = True,
        fresh: bool = True,
        relevant: bool = True,
        duplicate: bool = False,
    ) -> str:
        return route_editorial(
            self.store,
            story_id,
            decision,
            auto_publish_enabled=self.auto_publish_enabled,
            source_enabled=source_enabled,
            fresh=fresh,
            relevant=relevant,
            duplicate=duplicate,
        )

    def reject(self, story_id: str, *, actor: str = "operator") -> dict:
        return reject_story(self.store, story_id, actor=actor)


def shadow_ingest(records: list[dict], store: NewsroomV5Store, *, translator: Callable[[str], str] = translate_to_fa) -> dict:
    pipeline = NewsroomV5Pipeline(store, lightweight_translator=translator, auto_publish_enabled=False)
    results = [pipeline.ingest(record) for record in records]
    return {
        "ingested": sum(1 for item in results if not item.get("suppressed")),
        "suppressed": sum(1 for item in results if item.get("suppressed")),
        "published": 0,
        "results": results,
    }
