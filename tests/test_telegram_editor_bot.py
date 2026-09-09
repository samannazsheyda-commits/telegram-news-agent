from __future__ import annotations

import json
from pathlib import Path

from src.editorial_store import LocalEditorialStore, ReviewItem
from src.telegram_editor_bot import EditorBot, is_authorized_member, parse_edit_text


class Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): return None
    def json(self): return self.payload


class FakeSession:
    def __init__(self, member_status="administrator"):
        self.member_status = member_status
        self.posts = []
    def post(self, url, data=None, json=None, timeout=None):
        payload = json if json is not None else data
        self.posts.append((url, payload))
        if url.endswith('/getChatMember'):
            return Response({"ok": True, "result": {"status": self.member_status}})
        return Response({"ok": True, "result": {"message_id": 10}})


def _seed(tmp_path):
    queue = tmp_path / "data/editorial_queue.json"
    history = tmp_path / "data/editorial_history.json"
    store = LocalEditorialStore(queue, history)
    item = ReviewItem.for_news(
        news_key="n1", source="Reuters", source_url="https://example.com/n1",
        original_title="Iran launches missile toward Israel",
        original_summary="Officials confirm the launch.",
        persian_title="ایران یک موشک به سمت اسرائیل شلیک کرد",
        persian_body="مقام‌ها شلیک را تأیید کردند",
        published_at_source="2026-09-09T19:20:00+00:00",
    )
    store.upsert_queue(item)
    return store, item


def test_authorization_uses_bikhabaar_channel_admin_membership():
    assert is_authorized_member(123, "token", session=FakeSession("creator")) is True
    assert is_authorized_member(123, "token", session=FakeSession("administrator")) is True
    assert is_authorized_member(123, "token", session=FakeSession("member")) is False


def test_edit_text_requires_persian_title_and_optional_body():
    title, body = parse_edit_text("ایران یک موشک شلیک کرد\nجزئیات تازه منتشر شد")
    assert title == "ایران یک موشک شلیک کرد"
    assert body == "جزئیات تازه منتشر شد"
    assert parse_edit_text("Iran launched missile") == ("", "")


def test_queue_command_sends_real_inline_editor_controls(tmp_path):
    store, item = _seed(tmp_path)
    session = FakeSession()
    bot = EditorBot("token", store=store, command_dir=tmp_path / "panel_commands", session=session)
    bot.handle_message({"chat": {"id": 123}, "from": {"id": 123}, "text": "/queue"})
    sent = [payload for url, payload in session.posts if url.endswith('/sendMessage')]
    assert sent
    keyboard = sent[-1]["reply_markup"]
    assert "preview:" + item.id in keyboard
    assert "edit:" + item.id in keyboard
    assert "publish:" + item.id in keyboard
    assert "reject:" + item.id in keyboard


def test_publish_and_reject_callbacks_write_same_runtime_command_contract(tmp_path):
    store, item = _seed(tmp_path)
    session = FakeSession()
    command_dir = tmp_path / "panel_commands"
    bot = EditorBot("token", store=store, command_dir=command_dir, session=session)
    bot.handle_callback({"id": "cb1", "from": {"id": 123}, "message": {"chat": {"id": 123}}, "data": "publish:" + item.id})
    commands = list(command_dir.glob("*.json"))
    assert len(commands) == 1
    payload = json.loads(commands[0].read_text(encoding="utf-8"))
    assert payload["action"] == "publish"
    assert payload["item_id"] == item.id
    assert payload["title"] == item.persian_title


def test_edit_flow_updates_queue_then_preview_without_publishing(tmp_path):
    store, item = _seed(tmp_path)
    session = FakeSession()
    bot = EditorBot("token", store=store, command_dir=tmp_path / "panel_commands", session=session)
    bot.handle_callback({"id": "cb1", "from": {"id": 123}, "message": {"chat": {"id": 123}}, "data": "edit:" + item.id})
    bot.handle_message({"chat": {"id": 123}, "from": {"id": 123}, "text": "ایران موشک جدیدی شلیک کرد\nجزئیات شلیک تأیید شد"})
    edited = store.get_pending(item.id)
    assert edited is not None
    assert edited.persian_title == "ایران موشک جدیدی شلیک کرد"
    assert edited.persian_body == "جزئیات شلیک تأیید شد"
    assert list((tmp_path / "panel_commands").glob("*.json")) == []


def test_non_admin_cannot_read_queue_or_trigger_commands(tmp_path):
    store, item = _seed(tmp_path)
    session = FakeSession("member")
    command_dir = tmp_path / "panel_commands"
    bot = EditorBot("token", store=store, command_dir=command_dir, session=session)
    bot.handle_callback({"id": "cb", "from": {"id": 999}, "message": {"chat": {"id": 999}}, "data": "publish:" + item.id})
    assert not list(command_dir.glob("*.json"))
