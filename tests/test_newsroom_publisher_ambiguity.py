from __future__ import annotations

from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item
from src.newsroom_publisher import TelegramNewsroomPublisher


class _Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self.payload


class _AmbiguousMediaSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/sendPhoto"):
            raise TimeoutError("response lost after request")
        return _Response({"ok": True, "result": {"message_id": 999}})


class _DefinitiveMediaFailureSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/sendPhoto"):
            return _Response({"ok": False, "description": "Bad Request: wrong file identifier"}, status=400)
        return _Response({"ok": True, "result": {"message_id": 1000}})


def _item():
    return normalize_item(
        RawNewsItem(
            source="Reuters",
            source_url="https://example.com/source",
            source_item_id="post-1",
            published_at="2026-09-14T10:00:00+00:00",
            fetched_at="2026-09-14T10:00:05+00:00",
            title="Iran reopens airspace",
            summary="Flights resume after restrictions",
            media=[{"type": "image", "url": "https://cdn.example.com/photo.jpg"}],
            source_priority="protected",
        )
    )


def _translate(text):
    return {
        "Iran reopens airspace": "ایران حریم هوایی خود را بازگشایی کرد",
        "Flights resume after restrictions": "پروازها پس از محدودیت‌ها از سر گرفته شدند",
    }.get(text, "ترجمه فارسی معتبر")


def test_ambiguous_media_request_failure_never_falls_back_to_text():
    session = _AmbiguousMediaSession()
    publisher = TelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        session=session,
        translator=_translate,
    )

    result = publisher(_item())

    assert result["ok"] is False
    assert result["ambiguous"] is True
    assert [url.rsplit("/", 1)[-1] for url, _ in session.calls] == ["sendPhoto"]


def test_definitive_media_rejection_may_fall_back_to_text():
    session = _DefinitiveMediaFailureSession()
    publisher = TelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        session=session,
        translator=_translate,
    )

    result = publisher(_item())

    assert result == {"ok": True, "message_id": 1000}
    assert [url.rsplit("/", 1)[-1] for url, _ in session.calls] == [
        "sendPhoto",
        "sendMessage",
    ]
