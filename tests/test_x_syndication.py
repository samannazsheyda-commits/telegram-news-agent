import json

from src.x_syndication import parse_profile_timeline


def test_parse_profile_timeline_returns_fresh_direct_x_posts():
    payload = {
        "props": {
            "pageProps": {
                "timeline": {
                    "entries": [
                        {
                            "type": "tweet",
                            "content": {
                                "tweet": {
                                    "id_str": "1961234567890123456",
                                    "full_text": "Iran and the United States resume nuclear talks in Geneva",
                                    "created_at": "Sat Sep 05 08:20:00 +0000 2026",
                                    "user": {"screen_name": "Reuters"},
                                }
                            },
                        }
                    ]
                }
            }
        }
    }
    html = '<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script></html>'
    posts = parse_profile_timeline(html, "Reuters", "Reuters / X")
    assert len(posts) == 1
    post = posts[0]
    assert post.title == "Iran and the United States resume nuclear talks in Geneva"
    assert post.link == "https://x.com/Reuters/status/1961234567890123456"
    assert post.source == "Reuters / X"
    assert post.published == "Sat, 05 Sep 2026 08:20:00 +0000"


def test_parse_profile_timeline_filters_non_iran_posts():
    payload = {
        "props": {"pageProps": {"timeline": {"entries": [
            {"type": "tweet", "content": {"tweet": {
                "id_str": "1", "full_text": "Local sports result",
                "created_at": "Sat Sep 05 08:20:00 +0000 2026",
                "user": {"screen_name": "Reuters"},
            }}}
        ]}}}
    }
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>'
    assert parse_profile_timeline(html, "Reuters", "Reuters / X") == []
