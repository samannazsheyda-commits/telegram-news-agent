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


def test_text_publication_requires_telegram_ok_and_message_id_and_returns_final_persian_render():
    session = Session({"ok": True, "result": {"message_id": 321}})
    publisher = TelegramNewsroomPublisher("token", "@bikhabaar", session=session, translator=lambda x: f"فا {x}")
    result = publisher(item())
    assert result["ok"] is True
    assert result["message_id"] == 321
    assert result["persian_title"] == "فا Iran reopens airspace"
    assert result["persian_body"] == "فا Flights resume after restrictions"
    assert "فا Iran reopens airspace" in result["final_message"]
    assert "لینک منبع خبر" in result["final_message"]
    url, kwargs = session.calls[0]
    assert url.endswith("/sendMessage")
    assert kwargs["data"]["chat_id"] == "@bikhabaar"
    assert kwargs["data"]["text"] == result["final_message"]


def test_ok_false_never_returns_success_even_on_http_200():
    session = Session({"ok": False, "description": "Bad Request"})
    publisher = TelegramNewsroomPublisher("token", "@bikhabaar", session=session, translator=lambda x: f"فا {x}")
    result = publisher(item())
    assert result["ok"] is False
    assert "message_id" not in result


def test_truth_photo_uses_sendphoto_and_preserves_media_and_render_metadata():
    session = Session({"ok": True, "result": {"message_id": 777}})
    publisher = TelegramNewsroomPublisher("token", "@bikhabaar", session=session, translator=lambda x: f"فا {x}")
    result = publisher(item(
        source="Donald Trump / Truth Social",
        title="Iran Navy image",
        summary="Iran oil and Hormuz",
        media=[{"type": "image", "url": "https://cdn.example.com/photo.jpg", "description": "Iran Navy"}],
    ))
    assert result["ok"] is True
    assert result["message_id"] == 777
    assert result["persian_title"] == "فا Iran Navy image"
    assert result["final_message"]
    url, kwargs = session.calls[0]
    assert url.endswith("/sendPhoto")
    assert kwargs["data"]["photo"] == "https://cdn.example.com/photo.jpg"
    assert kwargs["data"]["caption"] == result["final_message"][:1024]


def test_iso_source_time_is_rendered_in_publication_text():
    session = Session({"ok": True, "result": {"message_id": 99}})
    publisher = TelegramNewsroomPublisher("token", "@bikhabaar", session=session, translator=lambda x: f"فا {x}")
    publisher(item(published="2026-09-07T21:00:00+00:00"))
    text = session.calls[0][1]["data"]["text"]
    assert "⏰" in text


def test_explosion_post_has_one_clean_persian_breaking_header_without_flags_or_handles():
    session = Session({"ok": True, "result": {"message_id": 555}})
    translations = {
        "UNCONFIRMED: 2 explosions heard in Jask, Hormozgan province, Iran 🇮🇷 @GeoPWatch":
            "گزارش‌های تاییدنشده از شنیده شدن ۲ انفجار در جاسک استان هرمزگان ایران 🇮🇷 @GeoPWatch",
        "Reports remain unconfirmed 🇮🇷": "این گزارش‌ها هنوز تایید نشده‌اند 🇮🇷",
    }
    publisher = TelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        session=session,
        translator=lambda text: translations.get(text, text),
    )
    result = publisher(item(
        source="GeoPWatch / Telegram",
        title="UNCONFIRMED: 2 explosions heard in Jask, Hormozgan province, Iran 🇮🇷 @GeoPWatch",
        summary="Reports remain unconfirmed 🇮🇷",
    ))
    text = session.calls[0][1]["data"]["text"]
    assert text == result["final_message"]
    assert text.startswith("💥 🔴 <b>خبر فوری | ژئوپی‌واچ / تلگرام: ")
    assert "GeoPWatch" not in text
    assert "/ Telegram" not in text
    assert "@GeoPWatch" not in text
    assert "🇮🇷" not in text
    assert "🇮🇱" not in text
    assert "🛑" not in text
    assert text.count("خبر فوری") == 1
