from src.fresh_x import parse_fxtwitter_timeline


def test_parse_fxtwitter_timeline_keeps_iran_posts_with_direct_status_url():
    payload = {
        "code": 200,
        "results": [
            {
                "type": "status",
                "id": "2096158936885874844",
                "url": "https://x.com/Reuters/status/2096158936885874844",
                "text": "Blasts heard near Iran's Kharg Island in Gulf, amid reports tanker hit",
                "created_at": "Sat Sep 05 08:50:09 +0000 2026",
            },
            {
                "type": "status",
                "id": "2096140054468968713",
                "url": "https://x.com/Reuters/status/2096140054468968713",
                "text": "US embassy issues health alert for Cuba amid oil blockade, sanctions",
                "created_at": "Sat Sep 05 07:35:08 +0000 2026",
            },
        ],
    }

    items = parse_fxtwitter_timeline(payload, "Reuters", "@Reuters")

    assert len(items) == 1
    assert items[0].key == "x:Reuters:2096158936885874844"
    assert items[0].source == "Reuters / X"
    assert items[0].link == "https://x.com/Reuters/status/2096158936885874844"
    assert items[0].published == "Sat, 05 Sep 2026 08:50:09 +0000"


def test_parser_rejects_status_from_wrong_profile():
    payload = {
        "code": 200,
        "results": [{
            "type": "status",
            "id": "1",
            "url": "https://x.com/Other/status/1",
            "text": "Iran update",
            "created_at": "Sat Sep 05 08:50:09 +0000 2026",
            "author": {"screen_name": "Other"},
        }],
    }
    assert parse_fxtwitter_timeline(payload, "Reuters", "@Reuters") == []
