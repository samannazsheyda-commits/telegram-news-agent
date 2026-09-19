from __future__ import annotations

from src.newsroom_v5_store import NewsroomV5Store
from src.newsroom_v5_translation import translate_story


def _story(story_id="s1", title="English headline", body="English body text with concrete details"):
    return {
        "id": story_id,
        "news_key": story_id,
        "source_id": "src",
        "source_name": "Source",
        "source_url": f"https://example.test/{story_id}",
        "source_item_id": story_id,
        "original_title": title,
        "original_body": body,
        "published_at_source": "2026-09-20T10:00:00+00:00",
        "state": "received",
    }


def test_lightweight_translation_success_advances_to_translated(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    store.upsert_story(_story())

    result = translate_story(store, "s1", lightweight=lambda text: "یک خبر مهم درباره ایران و منطقه")

    assert result["status"] == "translated"
    assert store.get_story("s1")["state"] == "translated"
    assert store.get_story("s1")["quality_passed"] == 1


def test_lightweight_failure_uses_ai_fallback(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    store.upsert_story(_story())

    result = translate_story(
        store,
        "s1",
        lightweight=lambda text: "",
        ai_fallback=lambda text: {"text": "ترجمه معتبر فارسی برای خبر مهم منطقه", "backend": "ai-test"},
    )

    assert result["status"] == "translated"
    assert store.get_story("s1")["translation_backend"] == "ai-test"


def test_all_translation_backends_fail_story_stays_durable_and_retry_is_scheduled(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    store.upsert_story(_story())

    result = translate_story(store, "s1", lightweight=lambda text: "", ai_fallback=lambda text: "")

    assert result["status"] == "retry"
    assert store.get_story("s1")["state"] == "received"
    jobs = store.conn.execute("SELECT * FROM jobs WHERE story_id='s1' AND kind='translate_story'").fetchall()
    assert len(jobs) == 1


def test_persian_source_is_normalized_without_ai(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    store.upsert_story(_story(
        title="تیتر فارسی معتبر درباره یک رویداد مهم",
        body="متن فارسی معتبر درباره جزئیات همان رویداد",
    ))
    calls = {"ai": 0}

    def ai(_):
        calls["ai"] += 1
        return "نباید صدا زده شود"

    result = translate_story(store, "s1", lightweight=lambda text: text, ai_fallback=ai)

    assert result["status"] == "translated"
    assert calls["ai"] == 0
