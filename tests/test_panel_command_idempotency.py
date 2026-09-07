from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src import panel_command_file


class FakeStore:
    def __init__(self, *args, **kwargs):
        self.item = SimpleNamespace(
            id="item-1",
            news_key="tg:tabzlive:102008",
            source="Tabz Live / Telegram",
            source_url="https://t.me/tabzlive/102008",
            original_title="Netanyahu on Iran",
            original_summary="",
            persian_title="نتانیاهو درباره ایران",
            persian_body="",
            published_at_source="Sun, 06 Sep 2026 16:03:00 GMT",
        )
        self.moved = []

    def get_pending(self, item_id):
        return self.item if item_id == self.item.id else None

    def move_to_history(self, item_id, **kwargs):
        self.moved.append((item_id, kwargs))
        return self.item


def _command(tmp_path):
    path = tmp_path / "command.json"
    path.write_text(
        json.dumps(
            {
                "action": "publish",
                "item_id": "item-1",
                "title": "نتانیاهو درباره ایران",
                "body": "متن خبر",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_publish_command_does_not_resend_when_source_is_already_in_own_channel(monkeypatch, tmp_path):
    store = FakeStore()
    monkeypatch.setattr(panel_command_file, "LocalEditorialStore", lambda *a, **k: store)
    monkeypatch.setattr(
        panel_command_file,
        "_source_already_published_in_channel",
        lambda url: True,
        raising=False,
    )
    monkeypatch.setattr(
        panel_command_file,
        "publish_review_item",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not resend Telegram message")),
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")

    panel_command_file.apply_command(_command(tmp_path))

    assert len(store.moved) == 1
    item_id, kwargs = store.moved[0]
    assert item_id == "item-1"
    assert kwargs["status"] == "published_manual"
    assert kwargs["final_persian_title"] == "نتانیاهو درباره ایران"
    assert kwargs["final_persian_body"] == "متن خبر"


def test_publish_command_fails_closed_if_channel_history_check_fails(monkeypatch, tmp_path):
    store = FakeStore()
    monkeypatch.setattr(panel_command_file, "LocalEditorialStore", lambda *a, **k: store)
    monkeypatch.setattr(
        panel_command_file,
        "_source_already_published_in_channel",
        lambda url: (_ for _ in ()).throw(RuntimeError("channel_check_failed")),
        raising=False,
    )
    monkeypatch.setattr(
        panel_command_file,
        "publish_review_item",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not publish when dedup check fails")),
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")

    with pytest.raises(RuntimeError, match="channel_check_failed"):
        panel_command_file.apply_command(_command(tmp_path))

    assert store.moved == []
