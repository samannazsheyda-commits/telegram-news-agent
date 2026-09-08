from src.fresh_x import MediaNewsItem, parse_fxtwitter_timeline
from src.newsroom_models import NormalizedNewsItem, RawNewsItem
from src.newsroom_publisher import TelegramNewsroomPublisher
from src.newsroom_raw_intake import news_item_to_raw
from src.newsroom_x import builtin_x_news_sources


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "result": {"message_id": 77}}


class _Session:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response()


def _normalized(raw):
    return NormalizedNewsItem(
        raw=raw,
        actors=[],
        locations=[],
        actions=[],
        objects=[],
        numeric_facts=[],
        topic_tags=[],
        quoted_speaker="",
        normalized_text=raw.title,
    )


def test_jason_brodsky_is_not_in_builtin_x_sources():
    handles = {row["handle"].lower() for row in builtin_x_news_sources()}
    assert "@jasonmbrodsky" not in handles


def test_fxtwitter_video_is_preserved_into_raw_media():
    payload = {
        "code": 200,
        "results": [{
            "type": "status",
            "id": "123",
            "author": {"screen_name": "CENTCOM"},
            "url": "https://x.com/CENTCOM/status/123",
            "text": "Video: Iran-related naval activity in the Persian Gulf",
            "created_at": "Tue Sep 08 18:00:00 +0000 2026",
            "media": {"videos": [{"variants": [
                {"content_type": "video/mp4", "bitrate": 832000, "url": "https://video.example/high.mp4"},
                {"content_type": "video/mp4", "bitrate": 256000, "url": "https://video.example/low.mp4"},
            ]}]},
        }],
    }
    items = parse_fxtwitter_timeline(payload, "CENTCOM", "@CENTCOM")
    assert len(items) == 1
    assert isinstance(items[0], MediaNewsItem)
    assert items[0].video_url == "https://video.example/high.mp4"
    raw = news_item_to_raw(items[0])
    assert {"type": "video", "url": "https://video.example/high.mp4"} in raw.media


def test_publisher_prefers_video_over_photo():
    raw = RawNewsItem(
        source="CENTCOM / X",
        source_url="https://x.com/CENTCOM/status/123",
        source_item_id="x:CENTCOM:123",
        published_at="Tue, 08 Sep 2026 18:00:00 +0000",
        fetched_at="2026-09-08T18:00:05+00:00",
        title="Iran-related naval activity",
        media=[
            {"type": "image", "url": "https://img.example/1.jpg"},
            {"type": "video", "url": "https://video.example/1.mp4"},
        ],
    )
    session = _Session()
    publisher = TelegramNewsroomPublisher("token", "@bikhabaar", session=session, translator=lambda text: "خبر آزمایشی")
    result = publisher(_normalized(raw))
    assert result == {"ok": True, "message_id": 77}
    assert session.calls
    url, kwargs = session.calls[0]
    assert url.endswith("/sendVideo")
    assert kwargs["data"]["video"] == "https://video.example/1.mp4"
