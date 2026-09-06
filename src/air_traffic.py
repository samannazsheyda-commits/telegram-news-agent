from __future__ import annotations

import argparse
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from PIL import ImageDraw
from staticmap import StaticMap

from .persian_datetime import gregorian_to_jalali, to_persian_digits

TEHRAN = ZoneInfo("Asia/Tehran")
CENTER_LAT = 30.0
CENTER_LON = 52.0
MAP_WIDTH = 700
MAP_HEIGHT = 1536
MAP_ZOOM = 5
OPENSKY_URL = "https://opensky-network.org/api/states/all"
QUERY_RADIUS_NM = 250
PROVIDERS = (
    "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}",
    "https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}",
)
# Only a fallback when the single full-frame OpenSky request is unavailable.
QUERY_CENTERS = (
    (48.0, 38.0),   # Caucasus / south Russia
    (43.0, 50.0),   # Caspian north
    (38.0, 46.0),   # NW Iran / Azerbaijan
    (36.0, 58.0),   # NE Iran / Turkmenistan
    (33.3, 44.4),   # Iraq
    (35.7, 51.4),   # Tehran
    (32.0, 64.0),   # Afghanistan
    (29.0, 48.0),   # Kuwait / SW Iran
    (28.5, 56.0),   # south/east Iran
    (26.0, 51.0),   # Bahrain / Qatar
    (25.2, 55.3),   # UAE
    (23.6, 58.4),   # Oman
    (21.0, 45.0),   # Saudi Arabia
    (15.4, 44.2),   # Yemen
    (10.0, 51.0),   # Gulf of Aden / Somalia
)
USER_AGENT = "bikhabaar-air-traffic/1.3"


def _tehran_jalali(now: datetime | None = None) -> tuple[str, str]:
    resolved = (now or datetime.now(timezone.utc)).astimezone(TEHRAN)
    jy, jm, jd = gregorian_to_jalali(resolved.year, resolved.month, resolved.day)
    months = (
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
    )
    date_text = f"{to_persian_digits(jd)} {months[jm - 1]} {to_persian_digits(jy)}"
    time_text = to_persian_digits(resolved.strftime("%H:%M"))
    return date_text, time_text


def build_caption(now: datetime | None = None) -> str:
    date_text, time_text = _tehran_jalali(now)
    return f"وضعیت ترافیک هوایی خاورمیانه\n⏰ {date_text} — {time_text}"


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


def filter_middle_east_aircraft(
    rows: Iterable[dict], *, max_seen_seconds: float = 120, bounds: dict[str, float] | None = None
) -> list[dict]:
    bounds = bounds or viewport_bounds()
    kept: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            lat = float(row.get("lat"))
            lon = float(row.get("lon"))
            seen_pos = float(row.get("seen_pos", row.get("seen", 9999)))
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
        lon = state[5]
        lat = state[6]
        if lat is None or lon is None:
            continue
        time_position = state[3] or state[4] or now_epoch
        try:
            seen_pos = max(0.0, now_epoch - float(time_position))
        except (TypeError, ValueError):
            seen_pos = 9999.0
        rows.append({
            "hex": str(state[0] or ""),
            "flight": str(state[1] or "").strip(),
            "lat": lat,
            "lon": lon,
            "seen_pos": seen_pos,
            "track": state[10] or 0.0,
        })
    return filter_middle_east_aircraft(rows, max_seen_seconds=120, bounds=bounds)


def _fetch_center(lat: float, lon: float, *, session=requests) -> list[dict]:
    errors: list[str] = []
    for template in PROVIDERS:
        url = template.format(lat=lat, lon=lon, radius=QUERY_RADIUS_NM)
        try:
            response = session.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("ac") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise ValueError("aircraft list missing")
            return rows
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("; ".join(errors))


def _fetch_point_fallback(*, session=requests) -> list[dict]:
    merged: dict[str, dict] = {}
    failures = 0
    for index, (lat, lon) in enumerate(QUERY_CENTERS):
        if index:
            time.sleep(1.05)
        try:
            rows = _fetch_center(lat, lon, session=session)
        except Exception as exc:
            failures += 1
            print(f"AIR_TRAFFIC_SOURCE_ERROR center=({lat},{lon}) error={exc}")
            continue
        for row in filter_middle_east_aircraft(rows):
            key = str(row.get("hex") or row.get("icao") or f"{row.get('lat')}:{row.get('lon')}")
            merged[key] = row
    if not merged:
        raise RuntimeError(f"no live air-traffic positions; failed_centers={failures}")
    print(f"AIR_TRAFFIC_FETCH provider=point-fallback aircraft={len(merged)} failed_centers={failures}")
    return list(merged.values())


def fetch_live_aircraft(*, session=requests) -> list[dict]:
    try:
        rows = _fetch_opensky_bbox(session=session)
        if rows:
            print(f"AIR_TRAFFIC_FETCH provider=opensky aircraft={len(rows)}")
            return rows
        print("AIR_TRAFFIC_SOURCE_ERROR provider=opensky error=empty_bbox")
    except Exception as exc:
        print(f"AIR_TRAFFIC_SOURCE_ERROR provider=opensky error={exc}")
    return _fetch_point_fallback(session=session)


def _screen_pixel(lon: float, lat: float) -> tuple[float, float]:
    x, y = _world_pixel(lon, lat, MAP_ZOOM)
    cx, cy = _world_pixel(CENTER_LON, CENTER_LAT, MAP_ZOOM)
    return MAP_WIDTH / 2 + (x - cx), MAP_HEIGHT / 2 + (y - cy)


def _plane_polygon(px: float, py: float, heading: float) -> list[tuple[float, float]]:
    shape = [
        (0, -10), (2.3, -4), (3.3, -1), (8.5, 1.8), (8.5, 3.8), (3.0, 3.2),
        (1.7, 7.0), (4.2, 9.0), (4.2, 10.5), (0, 9.0), (-4.2, 10.5), (-4.2, 9.0),
        (-1.7, 7.0), (-3.0, 3.2), (-8.5, 3.8), (-8.5, 1.8), (-3.3, -1), (-2.3, -4),
    ]
    angle = math.radians(heading % 360.0)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return [(px + x * cos_a - y * sin_a, py + x * sin_a + y * cos_a) for x, y in shape]


def render_air_traffic_map(aircraft: Iterable[dict], output_path: str | Path) -> Path:
    canvas = StaticMap(
        MAP_WIDTH,
        MAP_HEIGHT,
        url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    )
    rows = filter_middle_east_aircraft(aircraft, max_seen_seconds=120)
    if not rows:
        raise ValueError("no aircraft positions to render")

    image = canvas.render(zoom=MAP_ZOOM, center=(CENTER_LON, CENTER_LAT)).convert("RGB")
    draw = ImageDraw.Draw(image)
    for row in rows:
        lat = float(row["lat"])
        lon = float(row["lon"])
        px, py = _screen_pixel(lon, lat)
        if not (-20 <= px <= MAP_WIDTH + 20 and -20 <= py <= MAP_HEIGHT + 20):
            continue
        try:
            heading = float(row.get("track", row.get("true_heading", 0)) or 0)
        except (TypeError, ValueError):
            heading = 0.0
        draw.polygon(_plane_polygon(px, py, heading), fill="#ffc400", outline="#6f5800")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG")
    return path


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
            files={"photo": ("middle-east-air-traffic.png", image_file, "image/png")},
            timeout=45,
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(f"Telegram rejected air traffic post: {payload}")


def publish_air_traffic_snapshot(
    *,
    now: datetime | None = None,
    output_path: str | Path = "/tmp/middle-east-air-traffic.png",
) -> Path:
    aircraft = fetch_live_aircraft()
    path = render_air_traffic_map(aircraft, output_path)
    send_telegram_photo(
        path,
        build_caption(now),
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID", "@bikhabaar"),
    )
    return path


def _cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--output", default="/tmp/middle-east-air-traffic.png")
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
