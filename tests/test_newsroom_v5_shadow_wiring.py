from __future__ import annotations

from src.newsroom_models import RawNewsItem
from src.newsroom_v5_store import NewsroomV5Store
from src.panel_command_file import run_v5_shadow_items


def _raw():
    return RawNewsItem(
        source="Reuters",
        source_url="https://example.test/story",
        source_item_id="story-1",
        published_at="2026-09-20T10:00:00+00:00",
        fetched_at="2026-09-20T10:01:00+00:00",
        title="A concrete breaking news headline",
        summary="Details",
        media=[],
        source_priority="normal",
    )


def test_shadow_flag_off_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWSROOM_V5_SHADOW_PIPELINE", "false")
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    result = run_v5_shadow_items([_raw()], store=store)
    assert result["enabled"] is False
    assert store.conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0] == 0


def test_shadow_consumes_same_raw_item_without_publication(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWSROOM_V5_SHADOW_PIPELINE", "true")
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    result = run_v5_shadow_items([_raw()], store=store)
    assert result["enabled"] is True
    assert result["published"] == 0
    assert store.find_story(news_key="story-1") is not None
    assert store.conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 0
