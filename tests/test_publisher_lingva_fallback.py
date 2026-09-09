from src.newsroom_models import NormalizedNewsItem, RawNewsItem
from src.newsroom_publisher import TelegramNewsroomPublisher


class Resp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"translation": "ایران موشک‌های بالستیک شلیک کرد"}


class Session:
    def get(self, url, **kwargs):
        assert "/api/v1/en/fa/" in url
        return Resp()


def test_publisher_uses_lingva_when_primary_translator_is_empty():
    raw = RawNewsItem(
        source="Reuters / X",
        source_url="https://x.com/reuters/status/1",
        source_item_id="1",
        published_at="Wed, 09 Sep 2026 12:00:00 +0000",
        fetched_at="2026-09-09T12:00:00+00:00",
        title="Iran launched ballistic missiles",
        summary="",
        media=[],
        source_priority="protected",
    )
    item = NormalizedNewsItem(raw=raw, normalized_title=raw.title, normalized_summary="", language="en")
    publisher = TelegramNewsroomPublisher("token", "@channel", session=Session(), translator=lambda _text: "")
    message = publisher._message(item)
    assert "ایران موشک‌های بالستیک شلیک کرد" in message
