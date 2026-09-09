from src.newsroom_models import NormalizedNewsItem, RawNewsItem
from src.newsroom_publisher import TelegramNewsroomPublisher


class Response:
    def __init__(self, payload=None, fail=False):
        self.payload = payload or {}
        self.fail = fail
        self.status_code = 400 if fail else 200
        self.text = '{"ok":false,"description":"Bad Request: failed to get HTTP URL content"}' if fail else ""

    def raise_for_status(self):
        if self.fail:
            raise RuntimeError("http error")

    def json(self):
        return self.payload


class Session:
    def __init__(self):
        self.posts = []

    def post(self, url, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        self.posts.append(endpoint)
        if endpoint == "sendVideo":
            return Response(fail=True)
        return Response({"ok": True, "result": {"message_id": 321}})


def _item():
    raw = RawNewsItem(
        source="ClashReport / Telegram",
        source_url="https://t.me/clashreport/123",
        source_item_id="123",
        published_at="Wed, 09 Sep 2026 13:00:00 +0000",
        fetched_at="2026-09-09T13:00:01+00:00",
        title="Iran launched missiles",
        summary="",
        media=[{"type": "video", "url": "https://example.invalid/video.mp4"}],
        source_priority="protected",
    )
    return NormalizedNewsItem(
        raw=raw,
        actors=["Iran"],
        locations=[],
        actions=["launched"],
        objects=["missiles"],
        numeric_facts=[],
        topic_tags=["missile"],
        quoted_speaker="",
        normalized_text=raw.title.lower(),
    )


def test_media_failure_falls_back_to_text_message():
    session = Session()
    publisher = TelegramNewsroomPublisher(
        "token",
        "@channel",
        session=session,
        translator=lambda text: "ایران موشک شلیک کرد",
    )
    result = publisher(_item())
    assert result == {"ok": True, "message_id": 321}
    assert session.posts == ["sendVideo", "sendMessage"]
