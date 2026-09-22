from __future__ import annotations


SOURCE = {"id": "11111111-1111-1111-1111-111111111111", "display_name": "Example"}


def test_rss_collector_keeps_original_link_time_body_and_media():
    from bikhabar_v5.collectors.rss import collect_rss

    xml = """<?xml version="1.0"?>
    <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
      <channel><item>
        <title>Breaking headline</title>
        <link>https://example.com/news/1?utm_source=rss</link>
        <description><![CDATA[<p>Full summary text.</p>]]></description>
        <pubDate>Tue, 22 Sep 2026 10:30:00 GMT</pubDate>
        <media:content url="https://cdn.example.com/photo.jpg" type="image/jpeg" />
      </item></channel>
    </rss>"""

    rows = collect_rss(xml, SOURCE)

    assert len(rows) == 1
    assert rows[0]["source"] == "Example"
    assert rows[0]["source_url"] == "https://example.com/news/1"
    assert rows[0]["original_title"] == "Breaking headline"
    assert rows[0]["original_text"] == "Full summary text."
    assert rows[0]["published_at_source"] == "2026-09-22T10:30:00Z"
    assert rows[0]["media_json"] == {
        "items": [{"url": "https://cdn.example.com/photo.jpg", "type": "image/jpeg"}]
    }


def test_website_collector_reads_open_graph_and_article_copy():
    from bikhabar_v5.collectors.website import collect_website

    html = """
      <html><head>
        <meta property="og:title" content="Site headline">
        <meta property="og:image" content="https://cdn.example.com/cover.webp">
        <meta property="article:published_time" content="2026-09-22T11:00:00+00:00">
      </head><body><article><p>First paragraph.</p><p>Second paragraph.</p></article></body></html>
    """

    row = collect_website(html, "https://example.com/story/2", SOURCE)

    assert row["original_title"] == "Site headline"
    assert row["original_text"] == "First paragraph.\n\nSecond paragraph."
    assert row["published_at_source"] == "2026-09-22T11:00:00Z"
    assert row["media_json"]["items"][0]["url"] == "https://cdn.example.com/cover.webp"


def test_x_collector_preserves_post_identity_and_media():
    from bikhabar_v5.collectors.x import collect_x_posts

    rows = collect_x_posts(
        [
            {
                "id": "19001",
                "text": "Post text",
                "created_at": "2026-09-22T11:20:00Z",
                "author_username": "ExampleAccount",
                "media": [{"url": "https://pbs.twimg.com/media/a.jpg", "type": "photo"}],
            }
        ],
        SOURCE,
    )

    assert rows[0]["source_url"] == "https://x.com/ExampleAccount/status/19001"
    assert rows[0]["original_title"] == "Post text"
    assert rows[0]["media_json"]["items"][0]["type"] == "photo"


def test_telegram_collector_preserves_channel_message_link():
    from bikhabar_v5.collectors.telegram import collect_telegram_messages

    rows = collect_telegram_messages(
        [
            {
                "message_id": 44,
                "text": "Telegram report",
                "date": "2026-09-22T11:30:00+00:00",
                "chat": {"username": "example_channel"},
                "media": {"url": "https://cdn.example.com/tg.mp4", "type": "video"},
            }
        ],
        SOURCE,
    )

    assert rows[0]["source_url"] == "https://t.me/example_channel/44"
    assert rows[0]["original_text"] == "Telegram report"
    assert rows[0]["media_json"]["items"][0]["type"] == "video"


def test_manual_collector_and_service_ingest_share_canonical_contract():
    from bikhabar_v5.collector_service import CollectorService
    from bikhabar_v5.collectors.manual import collect_manual

    class Core:
        def __init__(self):
            self.rows = []

        def ingest_story(self, row):
            self.rows.append(row)
            return {**row, "status": "NEW"}, len(self.rows) == 1

    candidate = collect_manual(
        {
            "title": "Manual headline",
            "body": "Manual body",
            "url": "https://example.com/manual?utm_campaign=x",
            "published_at": "2026-09-22T12:00:00Z",
        },
        SOURCE,
    )
    core = Core()
    result = CollectorService(core).ingest([candidate, candidate])

    assert candidate["source_id"] == SOURCE["id"]
    assert candidate["source_url"] == "https://example.com/manual"
    assert len(candidate["fingerprint"]) == 64
    assert result == {"received": 2, "inserted": 1, "duplicates": 1}
