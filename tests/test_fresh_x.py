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


def test_parser_suppresses_video_dependent_x_post_when_channel_has_no_video_attachment():
    payload = {
        "code": 200,
        "results": [{
            "type": "status",
            "id": "2096215788063498460",
            "url": "https://x.com/TankerTrackers/status/2096215788063498460",
            "text": "Video shows an Iranian NITC VLCC fully loaded at Kharg Island.",
            "created_at": "Sat Sep 05 12:36:00 +0000 2026",
            "author": {"screen_name": "TankerTrackers"},
            "media": {
                "videos": [{"type": "video", "url": "https://video.example/test.mp4"}],
            },
        }],
    }

    assert parse_fxtwitter_timeline(payload, "TankerTrackers", "@TankerTrackers") == []


def test_parser_keeps_same_tanker_claim_when_it_does_not_depend_on_video():
    payload = {
        "code": 200,
        "results": [{
            "type": "status",
            "id": "2096215788063498461",
            "url": "https://x.com/TankerTrackers/status/2096215788063498461",
            "text": "An Iranian NITC VLCC is fully loaded at Kharg Island.",
            "created_at": "Sat Sep 05 12:37:00 +0000 2026",
            "author": {"screen_name": "TankerTrackers"},
        }],
    }

    items = parse_fxtwitter_timeline(payload, "TankerTrackers", "@TankerTrackers")
    assert len(items) == 1
