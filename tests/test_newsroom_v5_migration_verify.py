from __future__ import annotations

import json

from src.newsroom_v5_migration import migrate_local_snapshot
from src.newsroom_v5_migration_verify import verify_local_snapshot
from src.newsroom_v5_store import NewsroomV5Store


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _minimal_snapshot(root):
    _write(root / "data/panel_live_feed.json", [
        {
            "id": "s1",
            "news_key": "k1",
            "source": "Reuters",
            "source_url": "https://example.test/s1",
            "persian_title": "خبر یک",
            "published_at_source": "2026-09-20T10:00:00+00:00",
        }
    ])
    _write(root / "data/editorial_queue.json", [])
    _write(root / "data/editorial_history.json", [])
    _write(root / "data/custom_sources.json", [])
    _write(root / "state.json", {})


def test_verifier_passes_matching_snapshot_and_fails_on_missing_story(tmp_path):
    root = tmp_path / "repo"
    _minimal_snapshot(root)
    store = NewsroomV5Store(tmp_path / "newsroom.db")
    migrate_local_snapshot(root, store, apply=True)

    report = verify_local_snapshot(root, store)
    assert report["ok"] is True
    assert report["unresolved_conflicts"] == []

    store.conn.execute("DELETE FROM translations WHERE story_id='s1'")
    store.conn.execute("DELETE FROM stories WHERE id='s1'")
    store.conn.commit()
    broken = verify_local_snapshot(root, store)
    assert broken["ok"] is False
    assert broken["unresolved_conflicts"]
