from __future__ import annotations

import json
from pathlib import Path

import src.panel_command_file as command_file
import src.panel_command_router as router


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_luna_preview_saves_final_copy_without_publishing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(
        Path("data/panel_live_feed.json"),
        [
            {
                "item_id": "story-1",
                "news_key": "key-1",
                "source": "Reuters",
                "source_url": "https://example.com/story-1",
                "original_title": "Iran announces a new regional decision",
                "original_summary": "The decision was announced on Friday.",
                "published_at_source": "2026-09-18T12:00:00+00:00",
            }
        ],
    )
    _write(Path("data/editorial_queue.json"), [])
    _write(
        Path("panel_commands/cmd-preview.json"),
        {
            "command_id": "cmd-preview",
            "action": "luna_preview",
            "item_id": "story-1",
            "news_key": "key-1",
            "source": "Reuters",
            "source_url": "https://example.com/story-1",
            "original_title": "Iran announces a new regional decision",
            "original_body": "The decision was announced on Friday.",
        },
    )

    monkeypatch.setattr(
        command_file,
        "_finalize_manual_copy_with_luna",
        lambda title, body: ("ایران تصمیم منطقه‌ای تازه‌ای اعلام کرد", "این تصمیم روز جمعه اعلام شد"),
    )

    def _must_not_publish(**kwargs):
        raise AssertionError("luna_preview must never publish to Telegram")

    monkeypatch.setattr(command_file, "publish_manual_story", _must_not_publish)

    result = router.apply_command("panel_commands/cmd-preview.json")

    assert result["status"] == "succeeded"
    assert result["action"] == "luna_preview"
    assert result["telegram_message_id"] is None
    assert result["review_url"] == "/review/story-1"

    queue = _read(Path("data/editorial_queue.json"))
    assert len(queue) == 1
    assert queue[0]["id"] == "story-1"
    assert queue[0]["status"] == "pending"
    assert queue[0]["luna_status"] == "ready"
    assert queue[0]["final_persian_title"] == "ایران تصمیم منطقه‌ای تازه‌ای اعلام کرد"
    assert queue[0]["final_persian_body"] == "این تصمیم روز جمعه اعلام شد"


def test_publish_final_uses_previewed_copy_without_running_luna_again(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(
        Path("data/editorial_queue.json"),
        [
            {
                "id": "story-2",
                "item_id": "story-2",
                "news_key": "key-2",
                "source": "Reuters",
                "source_url": "https://example.com/story-2",
                "original_title": "Original English title",
                "original_summary": "Original English body",
                "persian_title": "تیتر نهایی تأییدشده",
                "persian_body": "متن نهایی تأییدشده",
                "final_persian_title": "تیتر نهایی تأییدشده",
                "final_persian_body": "متن نهایی تأییدشده",
                "status": "pending",
                "luna_status": "ready",
            }
        ],
    )
    _write(Path("data/editorial_history.json"), [])
    _write(Path("data/panel_live_feed.json"), [])
    _write(
        Path("panel_commands/cmd-publish.json"),
        {
            "command_id": "cmd-publish",
            "action": "publish_final",
            "item_id": "story-2",
            "title": "تیتر نهایی تأییدشده",
            "body": "متن نهایی تأییدشده",
        },
    )

    monkeypatch.setattr(
        command_file,
        "_finalize_manual_copy_with_luna",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("publish_final must not run Luna again")),
    )
    captured = {}

    def _publish_manual_story(**kwargs):
        captured.update(kwargs)
        return {"status": "succeeded", "story_id": "v3-story-2", "telegram_message_id": 12345}

    monkeypatch.setattr(command_file, "publish_manual_story", _publish_manual_story)

    result = router.apply_command("panel_commands/cmd-publish.json")

    assert result["status"] == "succeeded"
    assert result["action"] == "publish_final"
    assert captured["title"] == "تیتر نهایی تأییدشده"
    assert captured["body"] == "متن نهایی تأییدشده"
    assert captured["item_id"] == "story-2"
