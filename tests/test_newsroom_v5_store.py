from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from src.newsroom_v5_db import SCHEMA_VERSION, connect, initialize, transaction
from src.newsroom_v5_store import NewsroomV5Store


def _story(story_id: str, *, published_at: str = "2026-09-20T10:00:00+00:00", state: str = "received") -> dict:
    return {
        "id": story_id,
        "news_key": f"news:{story_id}",
        "source_id": "reuters",
        "source_name": "Reuters",
        "source_url": f"https://example.test/{story_id}",
        "source_item_id": story_id,
        "original_title": f"Title {story_id}",
        "original_body": "Body",
        "published_at_source": published_at,
        "discovered_at": "2026-09-20T10:01:00+00:00",
        "state": state,
    }


def test_initialize_creates_schema_wal_and_foreign_keys(tmp_path):
    db_path = tmp_path / "newsroom.db"
    conn = connect(db_path)
    initialize(conn)

    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("SELECT version FROM schema_meta").fetchone()[0] == SCHEMA_VERSION

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "stories",
        "translations",
        "editorial_decisions",
        "publications",
        "story_tombstones",
        "sources",
        "jobs",
        "luna_conversations",
        "audit_log",
    } <= tables


def test_transaction_rolls_back_partial_state(tmp_path):
    conn = connect(tmp_path / "rollback.db")
    initialize(conn)

    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute(
                "INSERT INTO stories(id, state, created_at, updated_at) VALUES (?, ?, ?, ?)",
                ("s1", "received", "now", "now"),
            )
            raise RuntimeError("boom")

    assert conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0] == 0


def test_publication_idempotency_key_is_unique(tmp_path):
    store = NewsroomV5Store(tmp_path / "idempotency.db")
    store.upsert_story(_story("s1", state="review"))
    store.set_translation("s1", title_fa="تیتر", body_fa="متن", backend="test", quality_passed=True)

    first = store.create_publication_once(
        "s1", idempotency_key="publish:s1", copy_mode="machine", title_fa="تیتر", body_fa="متن"
    )
    second = store.create_publication_once(
        "s1", idempotency_key="publish:s1", copy_mode="machine", title_fa="تیتر", body_fa="متن"
    )

    assert first["id"] == second["id"]
    assert store.conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 1


def test_review_is_persian_ready_terminal_free_and_cursor_ordered(tmp_path):
    store = NewsroomV5Store(tmp_path / "review.db")
    same_time = "2026-09-20T10:00:00+00:00"
    older = "2026-09-20T09:00:00+00:00"

    for story_id, when, state in [
        ("b", same_time, "review"),
        ("a", same_time, "review"),
        ("older", older, "review"),
        ("raw", "2026-09-20T11:00:00+00:00", "review"),
        ("published", "2026-09-20T12:00:00+00:00", "published"),
        ("rejected", "2026-09-20T13:00:00+00:00", "rejected"),
    ]:
        store.upsert_story(_story(story_id, published_at=when, state=state))

    for story_id in ("a", "b", "older", "published", "rejected"):
        store.set_translation(story_id, title_fa=f"تیتر {story_id}", body_fa="متن", backend="test", quality_passed=True)

    page1 = store.list_review(limit=2)
    assert [item["id"] for item in page1["items"]] == ["b", "a"]
    assert page1["next_cursor"]

    page2 = store.list_review(limit=2, cursor=page1["next_cursor"])
    assert [item["id"] for item in page2["items"]] == ["older"]
    assert page2["next_cursor"] is None


def test_transition_story_uses_expected_state_guard(tmp_path):
    store = NewsroomV5Store(tmp_path / "transition.db")
    store.upsert_story(_story("s1", state="received"))
    assert store.transition_story("s1", {"received"}, "translated") is True
    assert store.transition_story("s1", {"received"}, "review") is False
    assert store.get_story("s1")["state"] == "translated"


def test_exact_tombstones_match_news_key_or_exact_url_not_source(tmp_path):
    store = NewsroomV5Store(tmp_path / "tombstone.db")
    store.upsert_story(_story("s1", state="rejected"))
    store.add_story_tombstone(
        "s1",
        news_key="news:s1",
        source_url="https://example.test/s1",
        reason="rejected_manual",
    )

    assert store.is_tombstoned(news_key="news:s1") is True
    assert store.is_tombstoned(source_url="https://example.test/s1") is True
    assert store.is_tombstoned(news_key="news:other", source_url="https://example.test/other") is False


def test_jobs_claim_retry_and_finish(tmp_path):
    store = NewsroomV5Store(tmp_path / "jobs.db")
    store.upsert_story(_story("s1"))
    job = store.enqueue_job("translate_story", story_id="s1", payload={"x": 1})

    claimed = store.claim_jobs("translate_story", worker_id="worker-a", limit=10, lease_seconds=30)
    assert [row["id"] for row in claimed] == [job["id"]]
    assert store.claim_jobs("translate_story", worker_id="worker-b", limit=10, lease_seconds=30) == []

    store.retry_job(job["id"], error="temporary", delay_seconds=0)
    reclaimed = store.claim_jobs("translate_story", worker_id="worker-b", limit=10, lease_seconds=30)
    assert reclaimed[0]["attempt_count"] >= 1
    store.finish_job(job["id"])
    row = store.conn.execute("SELECT status FROM jobs WHERE id = ?", (job["id"],)).fetchone()
    assert row[0] == "done"


def test_cursor_is_deterministic_for_same_timestamp(tmp_path):
    store = NewsroomV5Store(tmp_path / "cursor.db")
    when = datetime.now(timezone.utc).isoformat()
    for story_id in ("c", "b", "a"):
        store.upsert_story(_story(story_id, published_at=when, state="review"))
        store.set_translation(story_id, title_fa="تیتر", body_fa="متن", backend="test", quality_passed=True)

    seen: list[str] = []
    cursor = None
    while True:
        page = store.list_review(limit=1, cursor=cursor)
        seen.extend(row["id"] for row in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == ["c", "b", "a"]
    assert len(seen) == len(set(seen))
