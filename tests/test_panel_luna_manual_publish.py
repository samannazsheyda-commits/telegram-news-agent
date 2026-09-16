from __future__ import annotations

from pathlib import Path

import pytest

import src.panel_command_router as router
from src.ai_newsroom import AIServiceError


def _queue_row() -> dict:
    return {
        "id": "story-1",
        "item_id": "story-1",
        "news_key": "news-1",
        "source": "Reuters",
        "source_url": "https://example.com/story-1",
        "original_title": "Iran announced a new operational development.",
        "original_summary": "The original English body contains the source facts.",
        "persian_title": "پیش‌نمایش آفلاین که نباید منتشر شود",
        "persian_body": "این متن فقط برای فهم اپراتور است",
        "published_at_source": "2026-09-16T12:00:00+00:00",
    }


def _patch_router_io(monkeypatch, row: dict) -> None:
    def fake_read_json(path: Path, default):
        if str(path).endswith("editorial_queue.json"):
            return [row]
        return default

    monkeypatch.setattr(router, "_read_json", fake_read_json)
    monkeypatch.setattr(router, "_finalize_editorial_publish", lambda payload, result: None)
    monkeypatch.setattr(
        router,
        "_write_result",
        lambda command_id, action, status, message, **kwargs: {
            "command_id": command_id,
            "action": action,
            "status": status,
            "message": message,
            **kwargs,
        },
    )


def test_manual_v3_publish_uses_original_source_then_luna_final_copy(monkeypatch):
    row = _queue_row()
    _patch_router_io(monkeypatch, row)

    seen = {}

    def fake_luna(original_title: str, original_body: str):
        seen["luna_title"] = original_title
        seen["luna_body"] = original_body
        return "تیتر نهایی لونا", "متن نهایی لونا"

    monkeypatch.setattr(router, "_finalize_manual_copy_with_luna", fake_luna)

    def fake_publish_manual_story(**kwargs):
        seen["publisher"] = kwargs
        return {
            "status": "succeeded",
            "story_id": "manual-story-1",
            "telegram_message_id": 123,
            "error": "",
        }

    monkeypatch.setattr(router, "publish_manual_story", fake_publish_manual_story)

    result = router._apply_v3_publish(
        {
            "command_id": "cmd-1",
            "action": "v3_publish",
            "item_id": "story-1",
            "news_key": "news-1",
            "source": "Reuters",
            "source_url": "https://example.com/story-1",
        }
    )

    assert seen["luna_title"] == row["original_title"]
    assert seen["luna_body"] == row["original_summary"]
    assert seen["publisher"]["title"] == "تیتر نهایی لونا"
    assert seen["publisher"]["body"] == "متن نهایی لونا"
    assert seen["publisher"]["title"] != row["persian_title"]
    assert seen["publisher"]["body"] != row["persian_body"]
    assert result["status"] == "succeeded"


def test_manual_v3_publish_fails_closed_before_telegram_when_luna_fails(monkeypatch):
    row = _queue_row()
    _patch_router_io(monkeypatch, row)
    publisher_called = False

    def failed_luna(original_title: str, original_body: str):
        raise AIServiceError("luna_manual_finalize_failed")

    def fake_publish_manual_story(**kwargs):
        nonlocal publisher_called
        publisher_called = True
        return {"status": "succeeded", "story_id": "should-not-exist", "telegram_message_id": 999}

    monkeypatch.setattr(router, "_finalize_manual_copy_with_luna", failed_luna)
    monkeypatch.setattr(router, "publish_manual_story", fake_publish_manual_story)

    with pytest.raises(AIServiceError, match="luna_manual_finalize_failed"):
        router._apply_v3_publish(
            {
                "command_id": "cmd-2",
                "action": "v3_publish",
                "item_id": "story-1",
                "source": "Reuters",
                "source_url": "https://example.com/story-1",
            }
        )

    assert publisher_called is False
