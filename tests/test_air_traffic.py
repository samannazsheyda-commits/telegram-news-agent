from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

import src.air_traffic as air_traffic
from src.air_traffic import (
    CENTER_LAT,
    CENTER_LON,
    MAP_HEIGHT,
    MAP_WIDTH,
    MAP_ZOOM,
    _fetch_center,
    _fetch_opensky_bbox,
    build_caption,
    fetch_live_aircraft,
    filter_middle_east_aircraft,
    render_air_traffic_map,
    viewport_bounds,
)


def test_caption_uses_exact_tehran_timestamp_to_the_second():
    now = datetime(2026, 9, 6, 17, 30, 45, tzinfo=timezone.utc)
    assert build_caption(now) == "وضعیت لحظه‌ای ترافیک هوایی ایران و منطقه\n⏰ ۱۵ شهریور ۱۴۰۵ — ۲۱:۰۰:۴۵"


def test_portrait_crop_matches_approved_iran_gulf_reference():
    bounds = viewport_bounds()
    assert MAP_WIDTH == 1080
    assert MAP_HEIGHT == 1640
    assert MAP_ZOOM == 6
    assert 31.0 <= CENTER_LAT <= 32.0
    assert 52.5 <= CENTER_LON <= 53.5
    assert 44.0 <= bounds["max_lat"] <= 47.0
    assert 14.0 <= bounds["min_lat"] <= 17.0
    assert 40.0 <= bounds["min_lon"] <= 42.5
    assert 64.0 <= bounds["max_lon"] <= 66.0


def test_filter_keeps_fresh_aircraft_across_approved_visible_crop():
    rows = [
        {"hex": "caspian", "lat": 44.0, "lon": 50.0, "seen_pos": 5},
        {"hex": "iran", "lat": 35.7, "lon": 51.4, "seen_pos": 5},
        {"hex": "iraq", "lat": 33.3, "lon": 44.4, "seen_pos": 5},
        {"hex": "gulf", "lat": 25.2, "lon": 55.3, "seen_pos": 10},
        {"hex": "afghanistan", "lat": 33.0, "lon": 64.0, "seen_pos": 5},
        {"hex": "yemen", "lat": 16.0, "lon": 48.0, "seen_pos": 5},
        {"hex": "old999", "lat": 30.0, "lon": 50.0, "seen_pos": 180},
        {"hex": "somalia", "lat": 5.0, "lon": 50.0, "seen_pos": 5},
        {"hex": "russia", "lat": 52.0, "lon": 50.0, "seen_pos": 2},
    ]
    kept = filter_middle_east_aircraft(rows, max_seen_seconds=60)
    assert [row["hex"] for row in kept] == ["caspian", "iran", "iraq", "gulf", "afghanistan", "yemen"]


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
                ["a3", "CASP3", None, 997, 997, 50.0, 44.0, None, False, None, 270],
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


class _PointResponse:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return {"ac": self._rows}


class _PointSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if "adsb.lol" in url:
            return _PointResponse([
                {"hex": "iran-a", "lat": 35.7, "lon": 51.4, "seen_pos": 1},
                {"hex": "shared", "lat": 35.6, "lon": 51.3, "seen_pos": 8},
            ])
        return _PointResponse([
            {"hex": "iran-b", "lat": 35.8, "lon": 51.5, "seen_pos": 2},
            {"hex": "shared", "lat": 35.65, "lon": 51.35, "seen_pos": 1},
        ])


def test_point_center_merges_both_adsb_providers_and_prefers_fresher_duplicate():
    session = _PointSession()
    rows = _fetch_center(35.7, 51.4, session=session)
    assert len(session.calls) == 2
    assert {row["hex"] for row in rows} == {"iran-a", "iran-b", "shared"}
    shared = next(row for row in rows if row["hex"] == "shared")
    assert shared["seen_pos"] == 1
    assert shared["lat"] == 35.65


def test_fetch_live_aircraft_merges_opensky_and_point_coverage(monkeypatch):
    monkeypatch.setattr(
        air_traffic,
        "_fetch_opensky_bbox",
        lambda session=None: [
            {"hex": "caspian", "lat": 44.0, "lon": 50.0, "seen_pos": 5},
            {"hex": "shared", "lat": 32.0, "lon": 52.0, "seen_pos": 20},
        ],
    )
    monkeypatch.setattr(
        air_traffic,
        "_fetch_point_fallback",
        lambda session=None: [
            {"hex": "iran", "lat": 35.7, "lon": 51.4, "seen_pos": 2},
            {"hex": "gulf", "lat": 25.2, "lon": 55.3, "seen_pos": 3},
            {"hex": "shared", "lat": 32.1, "lon": 52.1, "seen_pos": 1},
        ],
    )

    rows = fetch_live_aircraft(session=object())

    assert {row["hex"] for row in rows} == {"caspian", "iran", "gulf", "shared"}
    shared = next(row for row in rows if row["hex"] == "shared")
    assert shared["seen_pos"] == 1
    assert shared["lat"] == 32.1


def test_render_is_bright_1080x1920_with_timestamp_strip_and_yellow_aircraft(tmp_path):
    out = tmp_path / "air.png"
    now = datetime(2026, 9, 6, 17, 30, 45, tzinfo=timezone.utc)
    render_air_traffic_map(
        [{"hex": "abc123", "lat": 32.0, "lon": 51.0, "track": 90, "seen_pos": 1}],
        out,
        now=now,
    )
    image = Image.open(out).convert("RGB")
    assert image.size == (1080, 1920)

    pixels = list(image.getdata())
    yellowish = sum(1 for r, g, b in pixels if r > 190 and g > 150 and b < 90)
    red_dots = sum(1 for r, g, b in pixels if r > 190 and g < 100 and b < 100)
    assert yellowish >= 20
    assert red_dots == 0

    # The approved output is a bright map, not the dimmed Airplanes.live browser UI.
    map_crop = image.crop((0, 0, 1080, 1640))
    average_map_luma = sum(sum(pixel) / 3 for pixel in map_crop.getdata()) / (1080 * 1640)
    assert average_map_luma > 115

    # A dedicated light information strip must be physically embedded under the map.
    footer = image.crop((0, 1640, 1080, 1920))
    footer_pixels = list(footer.getdata())
    bright_footer = sum(1 for r, g, b in footer_pixels if r > 225 and g > 225 and b > 225)
    dark_ink = sum(1 for r, g, b in footer_pixels if r < 90 and g < 110 and b < 140)
    assert bright_footer > len(footer_pixels) * 0.55
    assert dark_ink > 500


def test_publish_refuses_implausibly_sparse_snapshot(monkeypatch, tmp_path):
    rows = [
        {"hex": f"a{i}", "lat": 30.0 + i * 0.01, "lon": 51.0, "track": 90, "seen_pos": 1}
        for i in range(3)
    ]
    monkeypatch.setattr(air_traffic, "fetch_live_aircraft", lambda: rows)
    sent = []
    monkeypatch.setattr(air_traffic, "send_telegram_photo", lambda *args, **kwargs: sent.append(args))

    with pytest.raises(RuntimeError, match="insufficient live aircraft"):
        air_traffic.publish_air_traffic_snapshot(output_path=tmp_path / "air.png")
    assert sent == []


def test_vps_timer_runs_exactly_at_20_00_00_00_and_02_00_tehran():
    timer = Path("deploy/bikhabar-air-traffic.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 16:30:00 UTC" in timer
    assert "OnCalendar=*-*-* 20:30:00 UTC" in timer
    assert "OnCalendar=*-*-* 22:30:00 UTC" in timer
    assert timer.count("OnCalendar=") == 3
    assert "AccuracySec=1s" in timer
    assert "RandomizedDelaySec=30" not in timer


def test_vps_air_traffic_service_publishes_instead_of_preview_only():
    service = Path("deploy/bikhabar-air-traffic.service").read_text(encoding="utf-8")
    assert "-m src.air_traffic --publish" in service
    assert "Temporary safety gate" not in service
