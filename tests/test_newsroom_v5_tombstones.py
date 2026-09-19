from __future__ import annotations

from src.newsroom_v5_identity import canonical_source_url, reject_story, story_is_tombstoned
from src.newsroom_v5_store import NewsroomV5Store


def _story(story_id, item_id, url):
    return {
        "id": story_id,
        "news_key": item_id,
        "source_id": "source-x",
        "source_name": "Source X",
        "source_item_id": item_id,
        "source_url": url,
        "original_title": story_id,
        "published_at_source": "2026-09-20T10:00:00+00:00",
        "state": "review",
    }


def test_reject_same_identity_stays_suppressed_but_same_source_new_story_is_allowed(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    a = _story("a", "item-a", "https://EXAMPLE.test/news/1?utm_source=x")
    store.upsert_story(a)
    reject_story(store, "a")

    assert store.get_story("a")["state"] == "rejected"
    assert story_is_tombstoned(store, news_key="item-a", source_url=a["source_url"])
    assert story_is_tombstoned(store, news_key="changed-id", source_url="https://example.test/news/1")
    assert not story_is_tombstoned(store, news_key="item-b", source_url="https://example.test/news/2")


def test_url_canonicalization_is_exact_not_topical():
    assert canonical_source_url("https://EXAMPLE.test/news/1/?utm_source=x#frag") == "https://example.test/news/1"
    assert canonical_source_url("https://example.test/news/2") != canonical_source_url("https://example.test/news/1")
