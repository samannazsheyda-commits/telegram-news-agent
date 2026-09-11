from __future__ import annotations

import argparse
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image, ImageDraw
from staticmap import StaticMap

from . import air_traffic as base

# Final user-approved portrait crop, derived from the latest reference screenshot.
# Geographic frame is intentionally wider/taller than the previous render while
# the delivered Telegram image stays 1080x1920.
CENTER_LAT = 31.5
CENTER_LON = 53.5
MAP_WIDTH = 1080
MAP_HEIGHT = 1640
FINAL_HEIGHT = 1920
MAP_ZOOM = 6
RENDER_WIDTH = 1320
RENDER_HEIGHT = 2004
PLANE_SCALE = 1.82
MIN_PUBLISH_AIRCRAFT = 8
MAX_POSITION_AGE_SECONDS = 120
BASEMAP_URL = "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png"

QUERY_RADIUS_NM = 250
QUERY_CENTERS = (
    (46.0, 44.0), (46.0, 55.0), (45.0, 65.0),
    (41.0, 43.0), (41.0, 53.0), (40.0, 63.0),
    (35.7, 51.4), (34.0, 43.5), (34.0, 63.5),
    (29.0, 48.0), (29.0, 57.0), (28.0, 66.0),
    (24.5, 45.0), (25.2, 55.3), (23.6, 58.4),
    (18.0, 43.0), (16.0, 50.0), (18.0, 61.0),
    (12.5, 46.0), (12.5, 56.0), (12.5, 66.0),
)


def _world_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    size = 256.0 * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * size
    lat = max(-85.05112878, min(85.05112878, lat))
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * size
    return x, y


def _lat_from_world_y(y: float, zoom: int) -> float:
    size = 256.0 * (2 ** zoom)
    n = math.pi - (2.0 * math.pi * y / size)
    return math.degrees(math.atan(math.sinh(n)))


def viewport_bounds() -> dict[str, float]:
    size = 256.0 * (2 ** MAP_ZOOM)
    cx, cy = _world_pixel(CENTER_LON, CENTER_LAT, MAP_ZOOM)
    half_w = RENDER_WIDTH / 2.0
    half_h = RENDER_HEIGHT / 2.0
    min_lon = ((cx - half_w) / size) * 360.0 - 180.0
    max_lon = ((cx + half_w) / size) * 360.0 - 180.0
    max_lat = _lat_from_world_y(cy - half_h, MAP_ZOOM)
    min_lat = _lat_from_world_y(cy + half_h, MAP_ZOOM)
    return {"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon}


def _seen_seconds(row: dict) -> float:
    value = row.get("seen_pos")
    if value is None:
        value = row.get("seen")
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 9999.0


def _aircraft_key(row: dict) -> str:
    identity = str(row.get("hex") or row.get("icao") or "").strip().lower()
    return identity or f"{row.get('lat')}:{row.get('lon')}"


def _merge_aircraft_rows(*groups: Iterable[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in groups:
        for row in group:
            if not isinstance(row, dict):
                continue
            key = _aircraft_key(row)
            current = merged.get(key)
            if current is None or _seen_seconds(row) < _seen_seconds(current):
                merged[key] = row
    return list(merged.values())


def filter_visible_aircraft(
    rows: Iterable[dict],
    *,
    max_seen_seconds: float = MAX_POSITION_AGE_SECONDS,
) -> list[dict]:
    bounds = viewport_bounds()
    kept: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            lat = float(row.get("lat"))
            lon = float(row.get("lon"))
        except (TypeError, ValueError):
            continue
        if _seen_seconds(row) > max_seen_seconds:
            continue
        if bounds["min_lat"] <= lat <= bounds["max_lat"] and bounds["min_lon"] <= lon <= bounds["max_lon"]:
            kept.append(row)
    return kept


def _fetch_opensky_bbox(*, session=requests) -> list[dict]:
    bounds = viewport_bounds()
    response = session.get(
        base.OPENSKY_URL,
        params={
            "lamin": round(bounds["min_lat"], 4),
            "lomin": round(bounds["min_lon"], 4),
            "lamax": round(bounds["max_lat"], 4),
            "lomax": round(bounds["max_lon"], 4),
        },
        headers={"User-Agent": base.USER_AGENT, "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    states = payload.get("states") if isinstance(payload, dict) else None
    if not isinstance(states, list):
        raise ValueError("OpenSky states missing")
    now_epoch = float(payload.get("time") or time.time())
    rows: list[dict] = []
    for state in states:
        if not isinstance(state, list) or len(state) < 11:
            continue
        lon, lat = state[5], state[6]
        if lat is None or lon is None:
            continue
        time_position = state[3] or state[4] or now_epoch
        try:
            seen_pos = max(0.0, now_epoch - float(time_position))
        except (TypeError, ValueError):
            seen_pos = 9999.0
        rows.append(
            {
                "hex": str(state[0] or ""),
                "flight": str(state[1] or "").strip(),
                "lat": lat,
                "lon": lon,
                "seen_pos": seen_pos,
                "track": state[10] or 0.0,
            }
        )
    return filter_visible_aircraft(rows)


def _fetch_center(lat: float, lon: float, *, session=requests) -> list[dict]:
    groups: list[list[dict]] = []
    errors: list[str] = []
    for template in base.PROVIDERS:
        url = template.format(lat=lat, lon=lon, radius=QUERY_RADIUS_NM)
        try:
            response = session.get(
                url,
                headers={"User-Agent": base.USER_AGENT, "Accept": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("ac") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise ValueError("aircraft list missing")
            groups.append(rows)
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    if not groups:
        raise RuntimeError("; ".join(errors) or "no point provider response")
    return _merge_aircraft_rows(*groups)


def _fetch_point_network(*, session=requests) -> list[dict]:
    groups: list[list[dict]] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="air-reference") as executor:
        futures = {
            executor.submit(_fetch_center, lat, lon, session=session): (lat, lon)
            for lat, lon in QUERY_CENTERS
        }
        for future in as_completed(futures):
            lat, lon = futures[future]
            try:
                rows = future.result()
            except Exception as exc:
                failures += 1
                print(f"AIR_TRAFFIC_SOURCE_ERROR center=({lat},{lon}) error={exc}")
                continue
            groups.append(filter_visible_aircraft(rows))
    merged = _merge_aircraft_rows(*groups)
    if not merged:
        raise RuntimeError(f"no live point-network positions; failed_centers={failures}")
    return merged


def fetch_live_aircraft(*, session=requests) -> list[dict]:
    groups: list[list[dict]] = []
    errors: list[str] = []
    loaders = {
        "opensky": lambda: _fetch_opensky_bbox(session=session),
        "point-network": lambda: _fetch_point_network(session=session),
    }
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="air-reference-sources") as executor:
        futures = {executor.submit(loader): name for name, loader in loaders.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                rows = future.result()
            except Exception as exc:
                errors.append(f"{name}:{exc}")
                print(f"AIR_TRAFFIC_SOURCE_ERROR provider={name} error={exc}")
                continue
            if rows:
                groups.append(rows)
                print(f"AIR_TRAFFIC_FETCH provider={name} aircraft={len(rows)}")
    merged = filter_visible_aircraft(_merge_aircraft_rows(*groups))
    if not merged:
        suffix = f"; {'; '.join(errors)}" if errors else ""
        raise RuntimeError("no live air-traffic positions from any provider" + suffix)
    print(f"AIR_TRAFFIC_FETCH merged aircraft={len(merged)} sources={len(groups)}")
    return merged


def _screen_pixel(lon: float, lat: float) -> tuple[float, float]:
    x, y = _world_pixel(lon, lat, MAP_ZOOM)
    cx, cy = _world_pixel(CENTER_LON, CENTER_LAT, MAP_ZOOM)
    return RENDER_WIDTH / 2 + (x - cx), RENDER_HEIGHT / 2 + (y - cy)


def _plane_polygon(px: float, py: float, heading: float, *, scale: float) -> list[tuple[float, float]]:
    shape = [
        (0, -10), (2.3, -4), (3.3, -1), (8.5, 1.8), (8.5, 3.8),
        (3.0, 3.2), (1.7, 7.0), (4.2, 9.0), (4.2, 10.5), (0, 9.0),
        (-4.2, 10.5), (-4.2, 9.0), (-1.7, 7.0), (-3.0, 3.2),
        (-8.5, 3.8), (-8.5, 1.8), (-3.3, -1), (-2.3, -4),
    ]
    angle = math.radians(heading % 360.0)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return [
        (
            px + (x * scale) * cos_a - (y * scale) * sin_a,
            py + (x * scale) * sin_a + (y * scale) * cos_a,
        )
        for x, y in shape
    ]


def _append_information_strip(map_image: Image.Image, *, now: datetime) -> Image.Image:
    image = Image.new("RGB", (MAP_WIDTH, FINAL_HEIGHT), "#f8fbff")
    image.paste(map_image, (0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, MAP_HEIGHT, MAP_WIDTH, MAP_HEIGHT + 4), fill="#d6e4f0")

    right = MAP_WIDTH - 46
    left = 44
    title_font = base._fit_rtl_font(
        draw, base.TITLE_FA, max_width=right - left, start_size=40, min_size=32, bold=True
    )
    meta_font = base._fit_rtl_font(
        draw, base._tehran_stamp(now), max_width=right - left, start_size=27, min_size=21
    )
    source_font = base._load_font(20)
    brand_font = base._fit_rtl_font(
        draw,
        "بی‌خبر | مانیتور تحولات ایران",
        max_width=right - left,
        start_size=24,
        min_size=20,
        bold=True,
    )

    base._draw_rtl(draw, (right, MAP_HEIGHT + 48), base.TITLE_FA, font=title_font, fill="#0b315d")
    base._draw_rtl(draw, (right, MAP_HEIGHT + 108), base._tehran_stamp(now), font=meta_font, fill="#304963")
    base._draw_rtl(
        draw,
        (right, MAP_HEIGHT + 160),
        "داده زنده: OpenSky + ADS-B + Airplanes.live",
        font=source_font,
        fill="#49657d",
    )
    draw.text(
        (left, MAP_HEIGHT + 202),
        "Map: © OpenStreetMap contributors © CARTO",
        font=base._load_font(16),
        fill="#6b7f91",
    )
    draw.line((left, MAP_HEIGHT + 226, right, MAP_HEIGHT + 226), fill="#d6e4f0", width=2)
    base._draw_rtl(
        draw,
        (right, MAP_HEIGHT + 248),
        "بی‌خبر | مانیتور تحولات ایران",
        font=brand_font,
        fill="#173f68",
    )
    return image


def render_air_traffic_map(
    aircraft: Iterable[dict],
    output_path: str | Path,
    *,
    now: datetime | None = None,
) -> Path:
    rows = filter_visible_aircraft(aircraft)
    if not rows:
        raise ValueError("no aircraft positions to render")

    canvas = StaticMap(RENDER_WIDTH, RENDER_HEIGHT, url_template=BASEMAP_URL)
    rendered = canvas.render(zoom=MAP_ZOOM, center=(CENTER_LON, CENTER_LAT)).convert("RGB")
    draw = ImageDraw.Draw(rendered)
    for row in rows:
        lat, lon = float(row["lat"]), float(row["lon"])
        px, py = _screen_pixel(lon, lat)
        if not (-40 <= px <= RENDER_WIDTH + 40 and -40 <= py <= RENDER_HEIGHT + 40):
            continue
        try:
            heading = float(row.get("track", row.get("true_heading", 0)) or 0)
        except (TypeError, ValueError):
            heading = 0.0
        draw.polygon(_plane_polygon(px, py, heading, scale=PLANE_SCALE + 0.18), fill="#5b4b00")
        draw.polygon(
            _plane_polygon(px, py, heading, scale=PLANE_SCALE),
            fill="#ffd000",
            outline="#8a6d00",
        )

    map_image = rendered.resize((MAP_WIDTH, MAP_HEIGHT), Image.Resampling.LANCZOS)
    captured_at = now or datetime.now(timezone.utc)
    final = _append_information_strip(map_image, now=captured_at)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    final.save(path, "PNG", optimize=True)
    return path


def _validate_rendered_image(path: str | Path) -> None:
    resolved = Path(path)
    if not resolved.is_file() or resolved.stat().st_size < 60_000:
        raise RuntimeError("air-traffic image validation failed: output missing or too small")
    with Image.open(resolved) as image:
        if image.size != (MAP_WIDTH, FINAL_HEIGHT):
            raise RuntimeError(f"air-traffic image validation failed: unexpected size {image.size}")


def build_air_traffic_preview(
    *,
    now: datetime | None = None,
    output_path: str | Path = "data/air_traffic_preview.png",
) -> dict:
    aircraft = fetch_live_aircraft()
    captured_at = now or datetime.now(timezone.utc)
    path = render_air_traffic_map(aircraft, output_path, now=captured_at)
    return {
        "message": base.build_caption(captured_at),
        "generated_at": captured_at.isoformat(),
        "aircraft_count": len(filter_visible_aircraft(aircraft)),
        "image_path": str(path),
        "source": "OpenSky / ADS-B / Airplanes.live",
    }


def publish_air_traffic_snapshot(
    *,
    now: datetime | None = None,
    output_path: str | Path = "/tmp/iran-region-live-air-traffic.png",
) -> Path:
    aircraft = fetch_live_aircraft()
    visible = filter_visible_aircraft(aircraft)
    if len(visible) < MIN_PUBLISH_AIRCRAFT:
        raise RuntimeError(
            f"insufficient live aircraft for safe publication: {len(visible)} < {MIN_PUBLISH_AIRCRAFT}"
        )
    captured_at = now or datetime.now(timezone.utc)
    path = render_air_traffic_map(visible, output_path, now=captured_at)
    _validate_rendered_image(path)
    base.send_telegram_photo(
        path,
        base.build_caption(captured_at),
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID", "@bikhabaar"),
    )
    return path


def _cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--output", default="/tmp/iran-region-live-air-traffic.png")
    args = parser.parse_args()
    if args.publish:
        publish_air_traffic_snapshot(output_path=args.output)
        return 0
    aircraft = fetch_live_aircraft()
    render_air_traffic_map(aircraft, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
