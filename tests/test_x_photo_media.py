from src.fresh_x import parse_fxtwitter_timeline


def test_fxtwitter_photo_is_preserved_on_news_item():
    payload = {
        "code": 200,
        "results": [
            {
                "type": "status",
                "id": "123",
                "url": "https://x.com/Reuters/status/123",
                "text": "Iran says a tanker was hit near Hormuz",
                "created_at": "Sat Sep 05 18:00:00 +0000 2026",
                "author": {"screen_name": "Reuters"},
                "media": {"photos": [{"url": "https://pbs.twimg.com/media/example.jpg"}]},
            }
        ],
    }

    items = parse_fxtwitter_timeline(payload, "Reuters", "@Reuters")

    assert len(items) == 1
    assert items[0].media_url == "https://pbs.twimg.com/media/example.jpg"


def test_fxtwitter_post_without_photo_keeps_empty_media_url():
    payload = {
        "code": 200,
        "results": [
            {
                "type": "status",
                "id": "124",
                "url": "https://x.com/Reuters/status/124",
                "text": "Iran says talks will continue in Tehran",
                "created_at": "Sat Sep 05 18:01:00 +0000 2026",
                "author": {"screen_name": "Reuters"},
            }
        ],
    }

    items = parse_fxtwitter_timeline(payload, "Reuters", "@Reuters")

    assert len(items) == 1
    assert items[0].media_url == ""
