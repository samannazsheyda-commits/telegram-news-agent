from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pytest

from src.newsroom_models import RawNewsItem
from src.newsroom_v3.store import NewsroomV3Store


def _runtime_module():
    try:
        return importlib.import_module("src.newsroom_v3.runtime")
    except ModuleNotFoundError:
        pytest.fail("Newsroom V3 runtime is not implemented yet")


def _item() -> RawNewsItem:
    return RawNewsItem(
        source="Reuters",
        source_url="https://www.reuters.com/world/middle-east/iran-missile-launch-runtime/",
        source_item_id="reuters-runtime-1",
        published_at="2026-09-14T10:00:00+00:00",
        fetched_at="2026-09-14T10:04:00+00:00",
        title="Iran launches missiles during military exercise near Strait of Hormuz",
        summary="Iranian forces launched missiles during a military exercise near the Strait of Hormuz.",
    )


def test_runtime_shadow_never_calls_publisher(tmp_path):
    runtime = _runtime_module()
    calls = []

    result = runtime.run_once(
        data_dir=tmp_path,
        fetchers=[lambda: [_item()]],
        now=datetime(2026, 9, 14, 10, 5, tzinfo=timezone.utc),
        shadow=True,
        publisher=lambda _story: calls.append(True),
    )

    assert result["mode"] == "shadow"
    assert result["processed"] == 1
    assert result["ready"] == 1
    assert result["telegram_writes"] == 0
    assert calls == []


def test_runtime_canary_publishes_at_most_requested_limit(tmp_path):
    runtime = _runtime_module()
    calls = []

    def publisher(story):
        calls.append(story.story_id)
        return {"ok": True, "message_id": 9000 + len(calls)}

    result = runtime.run_once(
        data_dir=tmp_path,
        fetchers=[lambda: [_item()]],
        now=datetime(2026, 9, 14, 10, 5, tzinfo=timezone.utc),
        shadow=False,
        publisher=publisher,
        publish_limit=1,
    )

    assert result["mode"] == "canary"
    assert result["telegram_writes"] == 1
    assert len(calls) == 1

    store = NewsroomV3Store(tmp_path / "newsroom_v3.sqlite3")
    story = store.get_story(result["story_ids"][0])
    assert story.publish_state == "published"
    assert story.telegram_message_id == 9001


def test_runtime_collects_source_failure_without_aborting_other_sources(tmp_path):
    runtime = _runtime_module()

    def broken():
        raise RuntimeError("source unavailable")

    result = runtime.run_once(
        data_dir=tmp_path,
        fetchers=[broken, lambda: [_item()]],
        now=datetime(2026, 9, 14, 10, 5, tzinfo=timezone.utc),
        shadow=True,
    )

    assert result["sources_ok"] == 1
    assert result["sources_failed"] == 1
    assert result["processed"] == 1
