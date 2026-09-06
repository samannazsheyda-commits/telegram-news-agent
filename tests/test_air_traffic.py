from datetime import datetime, timezone

from PIL import Image

from src.air_traffic import (
    CENTER_LAT,
    CENTER_LON,
    MAP_ZOOM,
    build_caption,
    filter_middle_east_aircraft,
    render_air_traffic_map,
)


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


def test_map_is_tightly_centered_on_iran_and_nearby_region():
    assert 30.0 <= CENTER_LAT <= 33.0
    assert 49.0 <= CENTER_LON <= 52.0
    assert MAP_ZOOM == 6


def test_render_uses_yellow_airplane_symbols_instead_of_red_dots(tmp_path):
    out = tmp_path / "air.png"
    render_air_traffic_map(
        [{"hex": "abc123", "lat": 32.0, "lon": 51.0, "track": 90}],
        out,
    )
    image = Image.open(out).convert("RGB")
    pixels = list(image.getdata())
    yellowish = sum(1 for r, g, b in pixels if r > 190 and g > 150 and b < 90)
    red_dots = sum(1 for r, g, b in pixels if r > 190 and g < 100 and b < 100)
    assert yellowish >= 20
    assert red_dots == 0
