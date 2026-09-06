from src.fresh_x import monitored_x_sources, parse_fxtwitter_timeline


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


def test_parser_keeps_self_contained_factual_claim_even_when_it_mentions_video():
    payload = {
        "code": 200,
        "results": [{
            "type": "status",
            "id": "2096215788063498460",
            "url": "https://x.com/TankerTrackers/status/2096215788063498460",
            "text": "Video shows an Iranian NITC VLCC was struck near Kharg Island and is on fire.",
            "created_at": "Sat Sep 05 12:36:00 +0000 2026",
            "author": {"screen_name": "TankerTrackers"},
            "media": {
                "videos": [{"type": "video", "url": "https://video.example/test.mp4"}],
            },
        }],
    }

    items = parse_fxtwitter_timeline(payload, "TankerTrackers", "@TankerTrackers")
    assert len(items) == 1
    assert "was struck" in items[0].title


def test_parser_still_suppresses_video_only_promo_or_contextless_cta():
    payload = {
        "code": 200,
        "results": [{
            "type": "status",
            "id": "2096215788063498469",
            "url": "https://x.com/TankerTrackers/status/2096215788063498469",
            "text": "Watch this video from Tehran for the full clip.",
            "created_at": "Sat Sep 05 12:36:30 +0000 2026",
            "author": {"screen_name": "TankerTrackers"},
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


def test_monitored_x_sources_use_active_current_accounts_not_dead_or_suspended_handles():
    handles = {source["handle"].lower() for source in monitored_x_sources()}
    assert "@petehegseth" in handles
    assert "@deptofwar" in handles
    assert "@secdef" not in handles
    assert "@dwnews" not in handles
    assert "@tasnimnews_fa" not in handles
    assert "@tasnimnews_en" not in handles
