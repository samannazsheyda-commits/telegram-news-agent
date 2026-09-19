from datetime import datetime, timedelta, timezone

from panel.live_api import _is_fresh_for_live_panel, _parse_time, _source_time


def test_parse_time_accepts_rss_rfc2822_dates():
    parsed = _parse_time("Sat, 19 Sep 2026 18:22:10 GMT")

    assert parsed == datetime(2026, 9, 19, 18, 22, 10, tzinfo=timezone.utc)


def test_source_time_prefers_source_publication_over_panel_update_time():
    row = {
        "published_at_source": "2026-09-19T17:00:00+00:00",
        "updated_at": "2026-09-19T18:00:00+00:00",
    }

    assert _source_time(row) == datetime(2026, 9, 19, 17, 0, tzinfo=timezone.utc)


def test_live_panel_keeps_recent_stories_for_six_hours():
    now = datetime(2026, 9, 19, 18, 0, tzinfo=timezone.utc)
    recent = {"published_at_source": (now - timedelta(hours=2)).isoformat()}
    expired = {"published_at_source": (now - timedelta(hours=7)).isoformat()}

    assert _is_fresh_for_live_panel(recent, now) is True
    assert _is_fresh_for_live_panel(expired, now) is False


def test_live_panel_rejects_implausibly_future_source_times():
    now = datetime(2026, 9, 19, 18, 0, tzinfo=timezone.utc)
    near_future = {"published_at_source": (now + timedelta(minutes=2)).isoformat()}
    bad_future = {"published_at_source": (now + timedelta(minutes=6)).isoformat()}

    assert _is_fresh_for_live_panel(near_future, now) is True
    assert _is_fresh_for_live_panel(bad_future, now) is False
