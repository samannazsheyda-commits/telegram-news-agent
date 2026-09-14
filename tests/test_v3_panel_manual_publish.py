from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.newsroom_v3.manual_publish import publish_manual_story
from src.newsroom_v3.production import _within_publish_interval


def _manual_kwargs(data_dir, publisher, now):
    return {
        "data_dir": data_dir,
        "item_id": "panel-item-1",
        "news_key": "news-key-1",
        "source": "Reuters",
        "source_url": "https://example.com/story-1",
        "title": "تیتر نهایی فارسی",
        "body": "متن نهایی فارسی",
        "published_at": (now - timedelta(minutes=2)).isoformat(),
        "publisher": publisher,
        "now": now,
    }


def test_manual_publish_uses_v3_outbox_and_persists_verified_message_id(tmp_path):
    data_dir = tmp_path / "data"
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    calls = []

    def publisher(story):
        calls.append(story)
        assert story.title == "تیتر نهایی فارسی"
        assert story.summary == "متن نهایی فارسی"
        assert story.source == "Reuters"
        assert story.source_url == "https://example.com/story-1"
        return {"ok": True, "result": {"message_id": 1701}}

    result = publish_manual_story(**_manual_kwargs(data_dir, publisher, now))

    assert result["status"] == "succeeded"
    assert result["telegram_message_id"] == 1701
    assert len(calls) == 1

    status = json.loads((data_dir / "newsroom_v3_production_status.json").read_text(encoding="utf-8"))
    assert status["last_publish_attempt_at"] == now.isoformat()
    assert status["last_published_at"] == now.isoformat()
    assert status["last_manual_publish_state"] == "succeeded"
    assert status["last_manual_telegram_message_id"] == 1701


def test_ambiguous_manual_publish_is_durable_and_never_automatically_retried(tmp_path):
    data_dir = tmp_path / "data"
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    first_calls = []

    def ambiguous(story):
        first_calls.append(story.story_id)
        return {"ok": False, "error": "network_timeout", "ambiguous": True}

    first = publish_manual_story(**_manual_kwargs(data_dir, ambiguous, now))
    assert first["status"] == "ambiguous"
    assert first["error"].startswith("ambiguous_remote_state:")
    assert len(first_calls) == 1

    second_calls = []

    def must_not_run(story):
        second_calls.append(story.story_id)
        return {"ok": True, "result": {"message_id": 9999}}

    second = publish_manual_story(
        **_manual_kwargs(data_dir, must_not_run, now + timedelta(seconds=15))
    )
    assert second["status"] == "ambiguous"
    assert second["error"].startswith("ambiguous_remote_state:")
    assert second_calls == []


def test_manual_attempt_timestamp_blocks_immediate_automatic_v3_write():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    state = {"last_publish_attempt_at": now.isoformat()}
    assert _within_publish_interval(
        state,
        now=now + timedelta(seconds=30),
        min_publish_interval_seconds=60,
    ) is True
