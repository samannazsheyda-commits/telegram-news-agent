from __future__ import annotations

import argparse
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont, features
from staticmap import StaticMap

from .persian_datetime import gregorian_to_jalali, to_persian_digits

TEHRAN = ZoneInfo("Asia/Tehran")

# Approved Telegram crop: Iran centered, Caspian at the top, Persian Gulf / Oman
# at the bottom, with Iraq/Kuwait on the left and Afghanistan on the right.
CENTER_LAT = 31.5
CENTER_LON = 53.0
MAP_WIDTH = 1080
MAP_HEIGHT = 1640
FINAL_HEIGHT = 1920
INFO_HEIGHT = FINAL_HEIGHT - MAP_HEIGHT
MAP_ZOOM = 6
PLANE_SCALE = 1.45
MIN_PUBLISH_AIRCRAFT = 8
MAX_POSITION_AGE_SECONDS = 120

OPENSKY_URL = "https://opensky-network.org/api/states/all"
QUERY_RADIUS_NM = 250
PROVIDERS = (
    "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}",
    "https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}",
)
# Point-provider coverage is deliberately limited to the approved visible crop.
QUERY_CENTERS = (
    (43.0, 50.0), (40.0, 59.0), (38.0, 46.0), (36.0, 58.0),
    (33.3, 44.4), (35.7, 51.4), (32.0, 64.0), (29.0, 48.0),
    (28.5, 56.0), (26.0, 51.0), (25.2, 55.3), (23.6, 58.4),
    (21.0, 45.0), (16.5, 48.0), (18.0, 61.0),
)
USER_AGENT = "bikhabaar-air-traffic/1.5"

TITLE_FA = "وضعیت لحظه‌ای ترافیک هوایی ایران و منطقه"
WEEKDAYS_FA = ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه")
MONTHS_FA = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)


def _resolved_tehran(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TEHRAN)


def _tehran_jalali(now: datetime | None = None) -> tuple[str, str]:
    resolved = _resolved_tehran(now)
    jy, jm, jd = gregorian_to_jalali(resolved.year, resolved.month, resolved.day)
    date_text = f"{to_persian_digits(jd)} {MONTHS_FA[jm - 1]} {to_persian_digits(jy)}"
    time_text = to_persian_digits(resolved.strftime("%H:%M:%S"))
    return date_text, time_text


def _tehran_stamp(now: datetime | None = None) -> str:
    resolved = _resolved_tehran(now)
    date_text, time_text = _tehran_jalali(resolved)
    return f"{WEEKDAYS_FA[resolved.weekday()]}، {date_text}  |  ساعت {time_text} (به وقت تهران)"


def build_caption(now: datetime | None = None) -> str:
    date_text, time_text = _tehran_jalali(now)
    return f"{TITLE_FA}\n⏰ {date_text} — {time_text}"


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
    half_w = MAP_WIDTH / 2.0
    half_h = MAP_HEIGHT / 2.0
    min_lon = ((cx - half_w) / size) * 360.0 - 180.0
    max_lon = ((cx + half_w) / size) * 360.0 - 180.0
    max_lat = _lat_from_world_y(cy - half_h, MAP_ZOOM)
    min_lat = _lat_from_world_y(cy + half_h, MAP_ZOOM)
    return {"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon}


def _aircraft_key(row: dict) -> str:
    identity = str(row.get("hex") or row.get("icao") or "").strip().lower()
    if identity:
        return identity
    return f"{row.get('lat')}:{row.get('lon')}"


def _seen_seconds(row: dict) -> float:
    value = row.get("seen_pos")
    if value is None:
        value = row.get("seen")
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 9999.0


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


def filter_middle_east_aircraft(
    rows: Iterable[dict],
    *,
    max_seen_seconds: float = MAX_POSITION_AGE_SECONDS,
    bounds: dict[str, float] | None = None,
) -> list[dict]:
    bounds = bounds or viewport_bounds()
    kept: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            lat = float(row.get("lat"))
            lon = float(row.get("lon"))
            seen_pos = _seen_seconds(row)
        except (TypeError, ValueError):
            continue
        if seen_pos > max_seen_seconds:
            continue
        if bounds["min_lat"] <= lat <= bounds["max_lat"] and bounds["min_lon"] <= lon <= bounds["max_lon"]:
            kept.append(row)
    return kept


def _fetch_opensky_bbox(*, session=requests) -> list[dict]:
    bounds = viewport_bounds()
    response = session.get(
        OPENSKY_URL,
        params={
            "lamin": round(bounds["min_lat"], 4),
            "lomin": round(bounds["min_lon"], 4),
            "lamax": round(bounds["max_lat"], 4),
            "lomax": round(bounds["max_lon"], 4),
        },
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
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
    return filter_middle_east_aircraft(rows, max_seen_seconds=MAX_POSITION_AGE_SECONDS, bounds=bounds)


def _fetch_center(lat: float, lon: float, *, session=requests) -> list[dict]:
    successful_groups: list[list[dict]] = []
    errors: list[str] = []
    for template in PROVIDERS:
        url = template.format(lat=lat, lon=lon, radius=QUERY_RADIUS_NM)
        try:
            response = session.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("ac") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise ValueError("aircraft list missing")
            successful_groups.append(rows)
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    if not successful_groups:
        raise RuntimeError("; ".join(errors) or "no point provider response")
    return _merge_aircraft_rows(*successful_groups)


def _fetch_point_fallback(*, session=requests) -> list[dict]:
    groups: list[list[dict]] = []
    failures = 0
    workers = min(8, max(1, len(QUERY_CENTERS)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="air-fallback") as executor:
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
            groups.append(filter_middle_east_aircraft(rows))
    merged = _merge_aircraft_rows(*groups)
    if not merged:
        raise RuntimeError(f"no live air-traffic positions; failed_centers={failures}")
    print(f"AIR_TRAFFIC_FETCH provider=point-network aircraft={len(merged)} failed_centers={failures}")
    return merged


def fetch_live_aircraft(*, session=requests) -> list[dict]:
    groups: list[list[dict]] = []
    errors: list[str] = []
    sources = {
        "opensky": lambda: _fetch_opensky_bbox(session=session),
        "point-network": lambda: _fetch_point_fallback(session=session),
    }
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="air-sources") as executor:
        futures = {executor.submit(loader): name for name, loader in sources.items()}
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
            else:
                print(f"AIR_TRAFFIC_SOURCE_ERROR provider={name} error=empty")

    merged = filter_middle_east_aircraft(
        _merge_aircraft_rows(*groups),
        max_seen_seconds=MAX_POSITION_AGE_SECONDS,
    )
    if not merged:
        suffix = f"; {'; '.join(errors)}" if errors else ""
        raise RuntimeError("no live air-traffic positions from any provider" + suffix)
    print(f"AIR_TRAFFIC_FETCH merged aircraft={len(merged)} sources={len(groups)}")
    return merged


def _screen_pixel(lon: float, lat: float) -> tuple[float, float]:
    x, y = _world_pixel(lon, lat, MAP_ZOOM)
    cx, cy = _world_pixel(CENTER_LON, CENTER_LAT, MAP_ZOOM)
    return MAP_WIDTH / 2 + (x - cx), MAP_HEIGHT / 2 + (y - cy)


def _plane_polygon(px: float, py: float, heading: float, *, scale: float = PLANE_SCALE) -> list[tuple[float, float]]:
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


def _font_path(*, bold: bool) -> Path:
    custom = os.environ.get("AIR_TRAFFIC_FONT_PATH", "").strip()
    candidates: list[Path] = []
    if custom:
        candidates.append(Path(custom))
    candidates.extend(
        Path(path)
        for path in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("air-traffic Persian font is unavailable")


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    if not features.check_feature("raqm"):
        raise RuntimeError("Pillow RAQM support is required for Persian air-traffic text")
    return ImageFont.truetype(
        str(_font_path(bold=bold)),
        size=size,
        layout_engine=ImageFont.Layout.RAQM,
    )


def _draw_rtl(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    fill: str,
    anchor: str = "ra",
) -> None:
    draw.text(xy, text, font=font, fill=fill, anchor=anchor, direction="rtl", language="fa")


def _draw_airplane_mark(draw: ImageDraw.ImageDraw) -> None:
    # Compact vector mark; no emoji/font dependency.
    x, y = 78, MAP_HEIGHT + 120
    points = [
        (x, y - 48), (x + 14, y - 18), (x + 55, y - 4), (x + 55, y + 12),
        (x + 13, y + 5), (x + 3, y + 48), (x - 11, y + 48), (x - 7, y + 5),
        (x - 46, y + 20), (x - 55, y + 8), (x - 16, y - 14), (x - 12, y - 48),
    ]
    draw.polygon(points, fill="#0c3b6e")


def _append_information_strip(map_image: Image.Image, *, now: datetime | None = None) -> Image.Image:
    image = Image.new("RGB", (MAP_WIDTH, FINAL_HEIGHT), "#f8fbff")
    image.paste(map_image, (0, 0))
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, MAP_HEIGHT, MAP_WIDTH, MAP_HEIGHT + 4), fill="#d6e4f0")
    draw.line((154, MAP_HEIGHT + 34, 154, FINAL_HEIGHT - 36), fill="#c6d7e5", width=3)
    _draw_airplane_mark(draw)

    title_font = _load_font(44, bold=True)
    meta_font = _load_font(28)
    brand_font = _load_font(27, bold=True)
    latin_font = _load_font(22)

    right = MAP_WIDTH - 46
    _draw_rtl(
        draw,
        (right, MAP_HEIGHT + 62),
        TITLE_FA,
        font=title_font,
        fill="#0b315d",
    )
    _draw_rtl(
        draw,
        (right, MAP_HEIGHT + 126),
        _tehran_stamp(now),
        font=meta_font,
        fill="#304963",
    )
    draw.text(
        (190, MAP_HEIGHT + 180),
        "LIVE DATA: OpenSky + ADS-B / Airplanes.live",
        font=latin_font,
        fill="#49657d",
    )
    draw.line((190, MAP_HEIGHT + 224, MAP_WIDTH - 46, MAP_HEIGHT + 224), fill="#d6e4f0", width=2)
    _draw_rtl(
        draw,
        (right, MAP_HEIGHT + 255),
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
    canvas = StaticMap(
        MAP_WIDTH,
        MAP_HEIGHT,
        url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    )
    rows = filter_middle_east_aircraft(aircraft, max_seen_seconds=MAX_POSITION_AGE_SECONDS)
    if not rows:
        raise ValueError("no aircraft positions to render")

    map_image = canvas.render(zoom=MAP_ZOOM, center=(CENTER_LON, CENTER_LAT)).convert("RGB")
    draw = ImageDraw.Draw(map_image)
    for row in rows:
        lat, lon = float(row["lat"]), float(row["lon"])
        px, py = _screen_pixel(lon, lat)
        if not (-30 <= px <= MAP_WIDTH + 30 and -30 <= py <= MAP_HEIGHT + 30):
            continue
        try:
            heading = float(row.get("track", row.get("true_heading", 0)) or 0)
        except (TypeError, ValueError):
            heading = 0.0

        # A dark outer silhouette makes the yellow aircraft readable over both land and sea.
        draw.polygon(
            _plane_polygon(px, py, heading, scale=PLANE_SCALE + 0.16),
            fill="#5b4b00",
        )
        draw.polygon(
            _plane_polygon(px, py, heading, scale=PLANE_SCALE),
            fill="#ffc400",
            outline="#8a6d00",
        )

    final = _append_information_strip(map_image, now=now)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    final.save(path, "PNG", optimize=True)
    return path


def _validate_publishable_aircraft(aircraft: Iterable[dict]) -> list[dict]:
    visible = filter_middle_east_aircraft(
        aircraft,
        max_seen_seconds=MAX_POSITION_AGE_SECONDS,
    )
    if len(visible) < MIN_PUBLISH_AIRCRAFT:
        raise RuntimeError(
            f"insufficient live aircraft for safe publication: {len(visible)} < {MIN_PUBLISH_AIRCRAFT}"
        )
    return visible


def _validate_rendered_image(path: str | Path) -> None:
    resolved = Path(path)
    if not resolved.is_file() or resolved.stat().st_size < 60_000:
        raise RuntimeError("air-traffic image validation failed: output missing or too small")
    with Image.open(resolved) as image:
        if image.size != (MAP_WIDTH, FINAL_HEIGHT):
            raise RuntimeError(f"air-traffic image validation failed: unexpected size {image.size}")


def send_telegram_photo(
    image_path: str | Path,
    caption: str,
    bot_token: str,
    chat_id: str,
    *,
    session=requests,
) -> None:
    if not bot_token or not chat_id:
        raise RuntimeError("Telegram credentials are required")
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with Path(image_path).open("rb") as image_file:
        response = session.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": ("iran-region-live-air-traffic.png", image_file, "image/png")},
            timeout=45,
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(f"Telegram rejected air traffic post: {payload}")


def build_air_traffic_preview(
    *,
    now: datetime | None = None,
    output_path: str | Path = "data/air_traffic_preview.png",
) -> dict:
    """Build a real live air-traffic snapshot for preview without publishing."""
    aircraft = fetch_live_aircraft()
    captured_at = now or datetime.now(timezone.utc)
    path = render_air_traffic_map(aircraft, output_path, now=captured_at)
    return {
        "message": build_caption(captured_at),
        "generated_at": captured_at.isoformat(),
        "aircraft_count": len(filter_middle_east_aircraft(aircraft)),
        "image_path": str(path),
        "source": "OpenSky / ADS-B / Airplanes.live",
    }


def publish_air_traffic_snapshot(
    *,
    now: datetime | None = None,
    output_path: str | Path = "/tmp/iran-region-live-air-traffic.png",
) -> Path:
    aircraft = fetch_live_aircraft()
    visible = _validate_publishable_aircraft(aircraft)
    captured_at = now or datetime.now(timezone.utc)
    path = render_air_traffic_map(visible, output_path, now=captured_at)
    _validate_rendered_image(path)
    send_telegram_photo(
        path,
        build_caption(captured_at),
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
