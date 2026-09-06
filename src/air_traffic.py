from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from staticmap import CircleMarker, StaticMap

from .persian_datetime import gregorian_to_jalali, to_persian_digits

TEHRAN = ZoneInfo("Asia/Tehran")
REGION_BOUNDS = {
    "min_lat": 12.0,
    "max_lat": 43.5,
    "min_lon": 25.0,
    "max_lon": 68.0,
}
CENTER_LAT = 28.5
CENTER_LON = 47.0
MAP_WIDTH = 1280
MAP_HEIGHT = 900
MAP_ZOOM = 4
ADSB_URLS = (
    "https://api.adsb.lol/v2/all",
    "https://api.airplanes.live/v2/all",
)
USER_AGENT = "bikhabaar-air-traffic/1.0"


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


def filter_middle_east_aircraft(
    rows: Iterable[dict], *, max_seen_seconds: float = 90
) -> list[dict]:
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
        if not (REGION_BOUNDS["min_lat"] <= lat <= REGION_BOUNDS["max_lat"]):
            continue
        if not (REGION_BOUNDS["min_lon"] <= lon <= REGION_BOUNDS["max_lon"]):
            continue
        kept.append(row)
    return kept


def fetch_live_aircraft(*, session=requests) -> list[dict]:
    errors: list[str] = []
    for url in ADSB_URLS:
        try:
            response = session.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("ac") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise ValueError("aircraft list missing")
            filtered = filter_middle_east_aircraft(rows)
            if filtered:
                return filtered
            raise ValueError("no fresh aircraft positions in region")
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("; ".join(errors) or "live ADS-B providers unavailable")


def render_air_traffic_map(aircraft: Iterable[dict], output_path: str | Path) -> Path:
    canvas = StaticMap(MAP_WIDTH, MAP_HEIGHT, url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    count = 0
    for row in aircraft:
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        canvas.add_marker(CircleMarker((lon, lat), "#e53935", 4))
        count += 1
    if count == 0:
        raise ValueError("no aircraft positions to render")
    image = canvas.render(zoom=MAP_ZOOM, center=(CENTER_LON, CENTER_LAT))
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
