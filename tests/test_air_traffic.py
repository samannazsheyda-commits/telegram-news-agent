from datetime import datetime, timezone

from PIL import Image

from src.air_traffic import (
    CENTER_LAT,
    CENTER_LON,
    MAP_HEIGHT,
    MAP_WIDTH,
    MAP_ZOOM,
    _fetch_opensky_bbox,
    build_caption,
    filter_middle_east_aircraft,
    render_air_traffic_map,
    viewport_bounds,
)


def test_caption_is_only_title_and_tehran_timestamp():
    now = datetime(2026, 9, 6, 17, 30, tzinfo=timezone.utc)
    assert build_caption(now) == "وضعیت ترافیک هوایی خاورمیانه\n⏰ ۱۵ شهریور ۱۴۰۵ — ۲۱:۰۰"


def test_portrait_crop_matches_requested_region():
    bounds = viewport_bounds()
    assert MAP_WIDTH == 700
    assert MAP_HEIGHT == 1536
    assert MAP_ZOOM == 5
    assert 29.0 <= CENTER_LAT <= 31.0
    assert 51.0 <= CENTER_LON <= 53.0
    assert bounds["max_lat"] >= 52.0
    assert bounds["min_lat"] <= 3.0
    assert bounds["min_lon"] <= 37.0
    assert bounds["max_lon"] >= 67.0


def test_filter_keeps_fresh_aircraft_across_whole_visible_crop():
    rows = [
        {"hex": "caspian", "lat": 45.0, "lon": 50.0, "seen_pos": 5},
        {"hex": "iran", "lat": 35.7, "lon": 51.4, "seen_pos": 5},
        {"hex": "iraq", "lat": 33.3, "lon": 44.4, "seen_pos": 5},
        {"hex": "gulf", "lat": 25.2, "lon": 55.3, "seen_pos": 10},
        {"hex": "pakistan", "lat": 30.0, "lon": 66.0, "seen_pos": 5},
        {"hex": "somalia", "lat": 5.0, "lon": 50.0, "seen_pos": 5},
        {"hex": "old999", "lat": 30.0, "lon": 50.0, "seen_pos": 180},
        {"hex": "outside", "lat": 48.0, "lon": 10.0, "seen_pos": 2},
    ]
    kept = filter_middle_east_aircraft(rows, max_seen_seconds=60)
    assert [row["hex"] for row in kept] == ["caspian", "iran", "iraq", "gulf", "pakistan", "somalia"]


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        now = 1000
        return {
            "time": now,
            "states": [
                ["a1", "IRAN1", None, 995, 995, 51.4, 35.7, None, False, None, 90],
                ["a2", "GULF2", None, 996, 996, 55.3, 25.2, None, False, None, 180],
                ["a3", "CASP3", None, 997, 997, 50.0, 45.0, None, False, None, 270],
            ],
        }


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response()


def test_opensky_fetch_uses_one_bbox_request_for_full_frame():
    session = _Session()
    rows = _fetch_opensky_bbox(session=session)
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url.endswith("/api/states/all")
    assert set(kwargs["params"]) == {"lamin", "lomin", "lamax", "lomax"}
    assert {row["hex"] for row in rows} == {"a1", "a2", "a3"}


def test_render_uses_yellow_airplane_symbols_instead_of_red_dots(tmp_path):
    out = tmp_path / "air.png"
    render_air_traffic_map(
        [{"hex": "abc123", "lat": 32.0, "lon": 51.0, "track": 90, "seen_pos": 1}],
        out,
    )
    image = Image.open(out).convert("RGB")
    assert image.size == (700, 1536)
    pixels = list(image.getdata())
    yellowish = sum(1 for r, g, b in pixels if r > 190 and g > 150 and b < 90)
    red_dots = sum(1 for r, g, b in pixels if r > 190 and g < 100 and b < 100)
    assert yellowish >= 20
    assert red_dots == 0
