import json
from pathlib import Path

import pytest

from src import panel_command_router


def _write_live_feed(path: Path, *, localized: bool = False) -> None:
    row = {
        "id": "story-1",
        "item_id": "story-1",
        "news_key": "story-1",
        "source": "Reuters",
        "source_url": "https://example.com/story-1",
        "title": "Iran announces a new air defence deployment",
        "body": "Officials said the deployment is active.",
        "persian_title": "ایران استقرار تازه پدافند هوایی را اعلام کرد" if localized else "",
        "persian_body": "مقام‌ها اعلام کردند این استقرار فعال است." if localized else "",
        "final_message": "ایران استقرار تازه پدافند هوایی را اعلام کرد\n\nمقام‌ها اعلام کردند این استقرار فعال است." if localized else "",
        "localized_at": "2026-09-15T20:00:00+00:00" if localized else "",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([row], ensure_ascii=False), encoding="utf-8")


def _command(path: Path, command_id: str = "loc-1") -> Path:
    payload = {
        "command_id": command_id,
        "action": "live_localize",
        "item_id": "story-1",
        "created_at": "2026-09-15T20:01:00+00:00",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_live_localize_command_persists_persian_copy_without_telegram(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_live_feed(tmp_path / "data" / "panel_live_feed.json")
    command = _command(tmp_path / "loc-1.json")

    translations = iter([
        "ایران استقرار تازه پدافند هوایی را اعلام کرد",
        "مقام‌ها اعلام کردند این استقرار فعال است.",
    ])
    monkeypatch.setattr(panel_command_router, "translate_to_fa", lambda text: next(translations), raising=False)

    telegram_calls = []
    monkeypatch.setattr(panel_command_router, "send_telegram", lambda *a, **k: telegram_calls.append((a, k)), raising=False)

    result = panel_command_router.apply_command(command)

    assert result["status"] == "succeeded"
    assert result["action"] == "live_localize"
    rows = json.loads((tmp_path / "data" / "panel_live_feed.json").read_text(encoding="utf-8"))
    row = rows[0]
    assert row["persian_title"] == "ایران استقرار تازه پدافند هوایی را اعلام کرد"
    assert row["persian_body"] == "مقام‌ها اعلام کردند این استقرار فعال است."
    assert row["final_message"]
    assert row["localized_at"]
    assert telegram_calls == []


def test_live_localize_command_is_idempotent_for_already_localized_story(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_live_feed(tmp_path / "data" / "panel_live_feed.json", localized=True)
    command = _command(tmp_path / "loc-2.json", command_id="loc-2")

    monkeypatch.setattr(
        panel_command_router,
        "translate_to_fa",
        lambda text: pytest.fail("translator must not run for an already-localized story"),
        raising=False,
    )

    result = panel_command_router.apply_command(command)

    assert result["status"] == "succeeded"
    rows = json.loads((tmp_path / "data" / "panel_live_feed.json").read_text(encoding="utf-8"))
    assert rows[0]["persian_title"] == "ایران استقرار تازه پدافند هوایی را اعلام کرد"
    assert rows[0]["final_message"]


def test_live_localize_command_fails_closed_when_translation_is_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_live_feed(tmp_path / "data" / "panel_live_feed.json")
    command = _command(tmp_path / "loc-3.json", command_id="loc-3")

    monkeypatch.setattr(panel_command_router, "translate_to_fa", lambda text: "", raising=False)

    result = panel_command_router.apply_command(command)

    assert result["status"] == "failed"
    rows = json.loads((tmp_path / "data" / "panel_live_feed.json").read_text(encoding="utf-8"))
    assert rows[0]["persian_title"] == ""
    assert rows[0]["final_message"] == ""
