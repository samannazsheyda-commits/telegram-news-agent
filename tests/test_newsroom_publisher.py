from src.newsroom_models import NormalizedNewsItem, RawNewsItem
from src.newsroom_publisher import TelegramNewsroomPublisher
from src.newsroom_normalize import normalize_item


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")
    def json(self):
        return self.payload


class Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.payload)


def item(*, media=None, source="Reuters", title="Iran reopens airspace", summary="Flights resume after restrictions", published="2026-09-07T21:00:00+00:00"):
    return normalize_item(RawNewsItem(
        source=source,
        source_url="https://example.com/source",
        source_item_id="post-1",
        published_at=published,
        fetched_at="2026-09-07T21:01:00+00:00",
        title=title,
        summary=summary,
        media=media or [],
        source_priority="protected" if "Truth" in source else "normal",
    ))


def test_text_publication_requires_telegram_ok_and_message_id():
    session = Session({"ok": True, "result": {"message_id": 321}})
    publisher = TelegramNewsroomPublisher("token", "@bikhabaar", session=session, translator=lambda x: f"فا {x}")
    result = publisher(item())
    assert result == {"ok": True, "message_id": 321}
    url, kwargs = session.calls[0]
    assert url.endswith("/sendMessage")
    assert kwargs["data"]["chat_id"] == "@bikhabaar"
    assert "لینک منبع خبر" in kwargs["data"]["text"]
    assert "فا Iran reopens airspace" in kwargs["data"]["text"]


def test_ok_false_never_returns_success_even_on_http_200():
    session = Session({"ok": False, "description": "Bad Request"})
    publisher = TelegramNewsroomPublisher("token", "@bikhabaar", session=session, translator=lambda x: f"فا {x}")
    result = publisher(item())
    assert result["ok"] is False
    assert "message_id" not in result


def test_truth_photo_uses_sendphoto_and_preserves_media():
    session = Session({"ok": True, "result": {"message_id": 777}})
    publisher = TelegramNewsroomPublisher("token", "@bikhabaar", session=session, translator=lambda x: f"فا {x}")
    result = publisher(item(
        source="Donald Trump / Truth Social",
        title="Iran Navy image",
        summary="Iran oil and Hormuz",
        media=[{"type": "image", "url": "https://cdn.example.com/photo.jpg", "description": "Iran Navy"}],
    ))
    assert result == {"ok": True, "message_id": 777}
    url, kwargs = session.calls[0]
    assert url.endswith("/sendPhoto")
    assert kwargs["data"]["photo"] == "https://cdn.example.com/photo.jpg"
    assert "caption" in kwargs["data"]


def test_iso_source_time_is_rendered_in_publication_text():
    session = Session({"ok": True, "result": {"message_id": 99}})
    publisher = TelegramNewsroomPublisher("token", "@bikhabaar", session=session, translator=lambda x: f"فا {x}")
    publisher(item(published="2026-09-07T21:00:00+00:00"))
    text = session.calls[0][1]["data"]["text"]
    assert "⏰" in text
