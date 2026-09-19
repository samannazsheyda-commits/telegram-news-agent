from __future__ import annotations

from dataclasses import dataclass

from src.newsroom_v5_pipeline import NewsroomV5Pipeline
from src.newsroom_v5_store import NewsroomV5Store


@dataclass
class Decision:
    importance: int = 80
    topic: str = "iran"
    publish: bool = False
    reason: str = "relevant"
    new_fact: bool = True
    priority_class: str = "high"
    confidence: float = 0.9


def raw(story_id="s1", *, url=None, source_item_id=None, published="2026-09-20T10:00:00+00:00"):
    return {
        "id": story_id,
        "news_key": source_item_id or story_id,
        "source_id": "src",
        "source_name": "Source",
        "source_url": url or f"https://example.test/{story_id}",
        "source_item_id": source_item_id or story_id,
        "original_title": "English headline with useful concrete details",
        "original_body": "English body with a concrete fact about Iran",
        "published_at_source": published,
    }


def test_untranslated_story_is_durable_but_never_visible_in_review(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    pipeline = NewsroomV5Pipeline(store, lightweight_translator=lambda _: "")
    result = pipeline.ingest(raw())
    assert result["state"] == "received"
    assert store.list_review()["items"] == []
    assert store.get_story("s1") is not None


def test_translation_then_editorial_routes_relevant_story_to_review_and_preserves_source_time(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    pipeline = NewsroomV5Pipeline(store, lightweight_translator=lambda _: "خبر فارسی معتبر درباره تحول مهم ایران")
    pipeline.ingest(raw())
    pipeline.process_translation("s1")
    outcome = pipeline.process_editorial("s1", Decision())
    assert outcome == "review"
    row = store.list_review()["items"][0]
    assert row["id"] == "s1"
    assert row["published_at_source"] == "2026-09-20T10:00:00+00:00"


def test_rejected_story_does_not_return_when_rescanned_even_if_item_id_changes(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    pipeline = NewsroomV5Pipeline(store, lightweight_translator=lambda _: "خبر فارسی معتبر برای انتشار")
    pipeline.ingest(raw("a", url="https://example.test/same", source_item_id="old"))
    pipeline.process_translation("a")
    pipeline.process_editorial("a", Decision())
    pipeline.reject("a")

    result = pipeline.ingest(raw("a-rescan", url="https://example.test/same", source_item_id="new"))
    assert result["suppressed"] is True
    assert store.get_story("a-rescan") is None


def test_rejection_does_not_block_later_story_from_same_source(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    pipeline = NewsroomV5Pipeline(store, lightweight_translator=lambda _: "خبر فارسی معتبر برای انتشار")
    pipeline.ingest(raw("a")); pipeline.process_translation("a"); pipeline.process_editorial("a", Decision()); pipeline.reject("a")
    result = pipeline.ingest(raw("b", published="2026-09-20T11:00:00+00:00"))
    assert result["suppressed"] is False
    assert store.get_story("b") is not None
