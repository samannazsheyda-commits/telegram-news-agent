from datetime import datetime, timezone

from src.air_traffic import build_caption, filter_middle_east_aircraft


def test_caption_is_only_title_and_tehran_timestamp():
    now = datetime(2026, 9, 6, 17, 30, tzinfo=timezone.utc)
    assert build_caption(now) == "وضعیت ترافیک هوایی خاورمیانه\n⏰ ۱۵ شهریور ۱۴۰۵ — ۲۱:۰۰"


def test_filter_middle_east_aircraft_keeps_only_fresh_positioned_rows():
    rows = [
        {"hex": "abc123", "lat": 35.7, "lon": 51.4, "seen_pos": 5},
        {"hex": "def456", "lat": 25.2, "lon": 55.3, "seen_pos": 10},
        {"hex": "old999", "lat": 30.0, "lon": 50.0, "seen_pos": 180},
        {"hex": "outside", "lat": 48.0, "lon": 10.0, "seen_pos": 2},
        {"hex": "missing", "seen_pos": 1},
    ]
    kept = filter_middle_east_aircraft(rows, max_seen_seconds=60)
    assert [row["hex"] for row in kept] == ["abc123", "def456"]
