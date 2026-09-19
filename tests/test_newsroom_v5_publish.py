from __future__ import annotations

import pytest

from src.newsroom_v5_publish import prepare_publication
from src.newsroom_v5_store import NewsroomV5Store


def _ready(store, story_id="s1"):
    store.upsert_story({
        "id": story_id,
        "news_key": story_id,
        "source_id": "src",
        "source_name": "Source",
        "source_url": f"https://example.test/{story_id}",
        "source_item_id": story_id,
        "original_title": "Original",
        "published_at_source": "2026-09-20T10:00:00+00:00",
        "state": "review",
    })
    store.set_translation(story_id, title_fa="تیتر فارسی", body_fa="متن فارسی", backend="test", quality_passed=True)


def test_same_idempotency_key_twice_creates_one_publication_and_one_send_job(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    _ready(store)
    first = prepare_publication(store, "s1", idempotency_key="publish:s1")
    second = prepare_publication(store, "s1", idempotency_key="publish:s1")
    assert first["id"] == second["id"]
    assert store.conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 1
    assert store.conn.execute("SELECT COUNT(*) FROM jobs WHERE kind='publish_story'").fetchone()[0] == 1
    assert store.get_story("s1")["state"] == "publishing"


def test_publication_freezes_exact_persian_payload(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    _ready(store)
    publication = prepare_publication(
        store,
        "s1",
        idempotency_key="publish:s1",
        copy_mode="manual",
        title_fa="تیتر نهایی",
        body_fa="متن نهایی",
    )
    store.set_translation("s1", title_fa="تیتر جدید", body_fa="متن جدید", backend="test", quality_passed=True)
    frozen = store.get_publication(publication["id"])
    assert frozen["title_fa"] == "تیتر نهایی"
    assert frozen["body_fa"] == "متن نهایی"


def test_already_published_story_cannot_create_second_send(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    _ready(store)
    store.transition_story("s1", {"review"}, "published")
    with pytest.raises(ValueError, match="not publishable"):
        prepare_publication(store, "s1", idempotency_key="publish:again")
    assert store.conn.execute("SELECT COUNT(*) FROM jobs WHERE kind='publish_story'").fetchone()[0] == 0


def test_invalid_copy_rolls_back_story_and_outbox(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    _ready(store)
    with pytest.raises(ValueError):
        prepare_publication(store, "s1", idempotency_key="bad", title_fa="")
    assert store.get_story("s1")["state"] == "review"
    assert store.conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 0
