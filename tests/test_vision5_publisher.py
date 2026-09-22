from __future__ import annotations

import pytest


class PublishStore:
    def __init__(self, story=None, attempt=None):
        self.story = story or {
            "id": "story-1",
            "status": "APPROVED",
            "final_title": "تیتر نهایی",
            "final_body": "متن نهایی خبر",
            "media_json": {},
        }
        self.attempt = attempt
        self.calls = []

    def prepare_publish(self, story_id, *, idempotency_key, copy_mode, payload, actor, allow_retry):
        self.calls.append(("prepare", story_id, idempotency_key, copy_mode, payload, actor, allow_retry))
        return self.story, self.attempt or {"id": "attempt-1", "status": "sending", "ambiguous": False}

    def complete_publish(self, story_id, attempt_id, *, telegram_message_id, actor):
        self.calls.append(("complete", story_id, attempt_id, telegram_message_id, actor))
        return {**self.story, "status": "PUBLISHED", "telegram_message_id": telegram_message_id}

    def fail_publish(self, story_id, attempt_id, *, error, ambiguous, actor):
        self.calls.append(("fail", story_id, attempt_id, error, ambiguous, actor))

    def reconcile_publish(self, story_id, attempt_id, *, telegram_message_id, actor):
        self.calls.append(("reconcile", story_id, attempt_id, telegram_message_id, actor))
        return {**self.story, "status": "PUBLISHED", "telegram_message_id": telegram_message_id}


class Telegram:
    def __init__(self, result=None, error=None):
        self.result = result or {"message_id": 998}
        self.error = error
        self.calls = []

    def send(self, *, text, media):
        self.calls.append({"text": text, "media": media})
        if self.error:
            raise self.error
        return self.result


def test_publisher_sends_final_copy_once_and_completes_attempt():
    from bikhabar_v5.publisher import TelegramPublisher

    store = PublishStore()
    telegram = Telegram()
    result = TelegramPublisher(store=store, telegram=telegram).publish(
        "story-1", actor="editor"
    )

    assert result["status"] == "PUBLISHED"
    assert telegram.calls == [{"text": "تیتر نهایی\n\nمتن نهایی خبر", "media": {}}]
    assert store.calls[0][0] == "prepare"
    assert store.calls[-1] == ("complete", "story-1", "attempt-1", 998, "editor")


def test_publisher_uses_photo_media_without_losing_final_caption():
    from bikhabar_v5.publisher import TelegramPublisher

    store = PublishStore(
        story={
            "id": "story-2",
            "status": "APPROVED",
            "final_title": "تیتر تصویر",
            "final_body": "شرح تصویر",
            "media_json": {"type": "photo", "url": "https://example.com/photo.jpg"},
        }
    )
    telegram = Telegram({"message_id": 999})

    TelegramPublisher(store=store, telegram=telegram).publish("story-2", actor="editor")

    assert telegram.calls[0]["media"]["type"] == "photo"
    assert "تیتر تصویر" in telegram.calls[0]["text"]


def test_publisher_selects_first_normalized_collector_media_item():
    from bikhabar_v5.publisher import TelegramPublisher

    store = PublishStore(
        story={
            "id": "story-3",
            "status": "APPROVED",
            "final_title": "تیتر تصویر",
            "final_body": "شرح",
            "media_json": {"items": [{"type": "image/jpeg", "url": "https://example.com/a.jpg"}]},
        }
    )
    telegram = Telegram()

    TelegramPublisher(store=store, telegram=telegram).publish("story-3", actor="editor")

    assert telegram.calls[0]["media"] == {"type": "photo", "url": "https://example.com/a.jpg"}


def test_ambiguous_timeout_is_persisted_and_never_auto_retried():
    from bikhabar_v5.publisher import AmbiguousPublishError, TelegramPublisher

    store = PublishStore()
    telegram = Telegram(error=TimeoutError("response timed out"))
    publisher = TelegramPublisher(store=store, telegram=telegram)

    with pytest.raises(AmbiguousPublishError):
        publisher.publish("story-1", actor="worker")

    assert store.calls[-1][0] == "fail"
    assert store.calls[-1][4] is True


def test_existing_ambiguous_attempt_requires_reconciliation_not_retry():
    from bikhabar_v5.publisher import AmbiguousPublishError, TelegramPublisher

    store = PublishStore(attempt={"id": "attempt-1", "status": "ambiguous", "ambiguous": True})
    telegram = Telegram()

    with pytest.raises(AmbiguousPublishError, match="reconciliation"):
        TelegramPublisher(store=store, telegram=telegram).publish(
            "story-1", actor="editor", allow_retry=True
        )

    assert telegram.calls == []


def test_operator_can_reconcile_ambiguous_attempt_with_verified_message_id():
    from bikhabar_v5.publisher import TelegramPublisher

    store = PublishStore(attempt={"id": "attempt-1", "status": "ambiguous", "ambiguous": True})
    result = TelegramPublisher(store=store, telegram=Telegram()).reconcile(
        "story-1", telegram_message_id=441, actor="editor"
    )

    assert result["status"] == "PUBLISHED"
    assert store.calls[-1] == ("reconcile", "story-1", "attempt-1", 441, "editor")


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, *, data, timeout):
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        return self.response


def test_telegram_client_selects_send_photo_and_validates_api_response():
    from bikhabar_v5.telegram import TelegramBotClient

    session = FakeSession(FakeResponse({"ok": True, "result": {"message_id": 77}}))
    client = TelegramBotClient(token="secret", chat_id="@channel", session=session, timeout_seconds=9)
    result = client.send(
        text="تیتر\n\nمتن",
        media={"type": "photo", "url": "https://example.com/a.jpg"},
    )

    assert result == {"message_id": 77}
    assert session.calls[0]["url"].endswith("/botsecret/sendPhoto")
    assert session.calls[0]["data"]["photo"] == "https://example.com/a.jpg"
    assert session.calls[0]["data"]["caption"] == "تیتر\n\nمتن"
    assert session.calls[0]["timeout"] == 9
