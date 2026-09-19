from __future__ import annotations

import json

from src.newsroom_v5_migration import migrate_local_snapshot
from src.newsroom_v5_store import NewsroomV5Store


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _snapshot(root):
    _write(root / "data/panel_live_feed.json", [
        {
            "id": "active",
            "news_key": "active-key",
            "source": "Reuters",
            "source_url": "https://example.test/active",
            "original_title": "Active original",
            "persian_title": "خبر فعال",
            "persian_body": "متن فارسی",
            "published_at_source": "2026-09-20T11:00:00+00:00",
        },
        {
            "id": "raw",
            "news_key": "raw-key",
            "source": "Reuters",
            "source_url": "https://example.test/raw",
            "original_title": "Raw English",
            "published_at_source": "2026-09-20T10:00:00+00:00",
        },
        {
            "id": "rejected",
            "news_key": "rejected-key",
            "source": "Reuters",
            "source_url": "https://example.test/rejected",
            "original_title": "Rejected duplicate projection",
            "published_at_source": "2026-09-20T09:00:00+00:00",
        },
        {
            "id": "later",
            "news_key": "later-key",
            "source": "Reuters",
            "source_url": "https://example.test/later",
            "original_title": "Later story",
            "persian_title": "خبر تازه بعدی",
            "published_at_source": "2026-09-20T12:00:00+00:00",
        },
    ])
    _write(root / "data/editorial_queue.json", [
        {
            "id": "active",
            "news_key": "active-key",
            "source": "Reuters",
            "source_url": "https://example.test/active",
            "persian_title": "خبر فعال",
            "persian_body": "متن فارسی",
            "status": "pending",
            "published_at_source": "2026-09-20T11:00:00+00:00",
        }
    ])
    _write(root / "data/editorial_history.json", [
        {
            "id": "published",
            "news_key": "published-key",
            "source": "AP",
            "source_url": "https://example.test/published",
            "persian_title": "خبر منتشرشده",
            "status": "published_manual",
            "telegram_message_id": 12345,
            "published_at_source": "2026-09-20T08:00:00+00:00",
        },
        {
            "id": "rejected",
            "news_key": "rejected-key",
            "source": "Reuters",
            "source_url": "https://example.test/rejected",
            "status": "rejected_manual",
            "published_at_source": "2026-09-20T09:00:00+00:00",
        },
    ])
    _write(root / "data/custom_sources.json", [
        {"id": "custom-1", "name": "Custom", "url": "https://custom.test/feed", "enabled": True}
    ])
    _write(root / "state.json", {"seen": ["anything"]})


def test_dry_run_reports_without_writing(tmp_path):
    root = tmp_path / "repo"
    _snapshot(root)
    store = NewsroomV5Store(tmp_path / "newsroom.db")

    report = migrate_local_snapshot(root, store, apply=False)

    assert report["stories"] >= 5
    assert store.conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0] == 0


def test_apply_is_idempotent_terminal_history_wins_and_rejection_is_narrow(tmp_path):
    root = tmp_path / "repo"
    _snapshot(root)
    store = NewsroomV5Store(tmp_path / "newsroom.db")

    first = migrate_local_snapshot(root, store, apply=True)
    second = migrate_local_snapshot(root, store, apply=True)

    assert second["stories"] == first["stories"]
    assert store.get_story("published")["state"] == "published"
    assert store.get_story("rejected")["state"] == "rejected"
    assert store.is_tombstoned(news_key="rejected-key", source_url="https://example.test/rejected")
    assert not store.is_tombstoned(news_key="later-key", source_url="https://example.test/later")
    assert store.get_story("later")["state"] in {"translated", "review"}
    assert store.conn.execute("SELECT COUNT(*) FROM stories WHERE id='rejected'").fetchone()[0] == 1
    assert store.conn.execute("SELECT COUNT(*) FROM sources WHERE id='custom-1'").fetchone()[0] == 1
