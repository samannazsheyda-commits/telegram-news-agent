from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .services import USER_AGENT, send_telegram

TEHRAN_TZ = ZoneInfo("Asia/Tehran")
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
STATE_PATH = Path(os.environ.get("WEATHER_STATE_PATH", "/var/lib/bikhabar/weather_state.json"))

CITIES = (
    ("تهران", 35.6892, 51.3890),
    ("کرج", 35.8400, 50.9391),
    ("مشهد", 36.2605, 59.6168),
    ("اصفهان", 32.6546, 51.6680),
    ("شیراز", 29.5918, 52.5837),
    ("تبریز", 38.0800, 46.2919),
    ("اهواز", 31.3183, 48.6706),
)

WMO = {
    0: ("☀️", "صاف"), 1: ("🌤️", "عمدتاً صاف"), 2: ("⛅", "نیمه‌ابری"), 3: ("☁️", "ابری"),
    45: ("🌫️", "مه"), 48: ("🌫️", "مه یخ‌زن"), 51: ("🌦️", "نم‌نم باران خفیف"),
    53: ("🌦️", "نم‌نم باران"), 55: ("🌧️", "نم‌نم باران شدید"), 61: ("🌦️", "باران خفیف"),
    63: ("🌧️", "باران"), 65: ("🌧️", "باران شدید"), 71: ("🌨️", "برف خفیف"),
    73: ("🌨️", "برف"), 75: ("❄️", "برف شدید"), 80: ("🌦️", "رگبار خفیف"),
    81: ("🌧️", "رگبار"), 82: ("⛈️", "رگبار شدید"), 95: ("⛈️", "رعدوبرق"),
    96: ("⛈️", "رعدوبرق همراه تگرگ"), 99: ("⛈️", "رعدوبرق شدید همراه تگرگ"),
}


def _tomorrow_index(daily: dict) -> int:
    dates = list(daily.get("time") or [])
    target = datetime.now(TEHRAN_TZ).date().isoformat()
    for idx, value in enumerate(dates):
        if value > target:
            return idx
    return 1 if len(dates) > 1 else 0


def _tomorrow_humidity(hourly: dict, date: str) -> int:
    times = list(hourly.get("time") or [])
    values = list(hourly.get("relative_humidity_2m") or [])
    selected = [float(values[i]) for i, t in enumerate(times) if i < len(values) and str(t).startswith(date)]
    return round(sum(selected) / len(selected)) if selected else 0


def fetch_city(name: str, lat: float, lon: float, *, session=requests) -> dict:
    response = session.get(
        OPEN_METEO,
        params={
            "latitude": lat,
            "longitude": lon,
            "timezone": "Asia/Tehran",
            "forecast_days": 3,
            "hourly": "relative_humidity_2m",
            "daily": ",".join((
                "weather_code", "temperature_2m_max", "temperature_2m_min",
                "precipitation_probability_max", "precipitation_sum",
                "wind_speed_10m_max", "wind_gusts_10m_max",
            )),
        },
        headers={"User-Agent": USER_AGENT}, timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    daily = payload.get("daily") or {}
    idx = _tomorrow_index(daily)

    def pick(key: str, default=0):
        values = daily.get(key) or []
        return values[idx] if idx < len(values) else default

    date = str(pick("time", ""))
    return {
        "name": name, "date": date,
        "code": int(pick("weather_code", 0) or 0),
        "tmax": round(float(pick("temperature_2m_max", 0) or 0)),
        "tmin": round(float(pick("temperature_2m_min", 0) or 0)),
        "pop": round(float(pick("precipitation_probability_max", 0) or 0)),
        "precip": round(float(pick("precipitation_sum", 0) or 0), 1),
        "humidity": _tomorrow_humidity(payload.get("hourly") or {}, date),
        "wind": round(float(pick("wind_speed_10m_max", 0) or 0)),
        "gust": round(float(pick("wind_gusts_10m_max", 0) or 0)),
    }


def _note(rows: list[dict]) -> str:
    hot = [r["name"] for r in rows if r.get("tmax", 0) >= 42]
    wet = [r["name"] for r in rows if r.get("pop", 0) >= 50 or r.get("precip", 0) >= 2]
    windy = [r["name"] for r in rows if r.get("gust", 0) >= 45]
    bits = []
    if hot: bits.append("گرمای شدید در " + "، ".join(hot))
    if wet: bits.append("احتمال بارش قابل‌توجه در " + "، ".join(wet))
    if windy: bits.append("تندباد قابل‌توجه در " + "، ".join(windy))
    return "؛ ".join(bits)


def format_digest(rows: list[dict]) -> str:
    if not rows:
        return ""
    date = rows[0].get("date") or "فردا"
    lines = [f"🌤️ <b>پیش‌بینی هوای فردا — {date}</b>"]
    for row in rows:
        icon, condition = WMO.get(int(row.get("code") or 0), ("🌡️", "نامشخص"))
        lines.append(
            f"{icon} <b>{row['name']}</b>: {condition} | 🌡️ {row['tmin']} تا {row['tmax']}°C | "
            f"💧 رطوبت {row.get('humidity', 0)}٪ | 🌧️ بارش {row['pop']}٪ ({row['precip']}mm) | "
            f"💨 باد {row['wind']}km/h، تندباد {row['gust']}km/h"
        )
    note = _note(rows)
    if note:
        lines.append(f"⚠️ <b>توضیح:</b> {note}.")
    lines.append("📡 منبع داده: Open-Meteo")
    return "\n".join(lines)


def _load_state() -> dict:
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def run(*, session=requests, force: bool = False) -> int:
    bot_token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID") or "@bikhabaar").strip()
    if not bot_token or not chat_id:
        print("WEATHER missing Telegram credentials", flush=True); return 2
    local_now = datetime.now(timezone.utc).astimezone(TEHRAN_TZ)
    state = _load_state(); day_key = local_now.date().isoformat()
    if not force and state.get("last_sent_local_day") == day_key:
        print("WEATHER already sent tonight", flush=True); return 0
    rows = []
    for city in CITIES:
        try: rows.append(fetch_city(*city, session=session))
        except Exception as exc: print(f"WEATHER fetch failed city={city[0]} error={type(exc).__name__}", flush=True)
    if len(rows) < 4:
        print(f"WEATHER insufficient city data count={len(rows)}", flush=True); return 3
    send_telegram(format_digest(rows), bot_token, chat_id, session=session)
    state["last_sent_local_day"] = day_key; state["last_sent_at"] = datetime.now(timezone.utc).isoformat(); _save_state(state)
    print(f"WEATHER sent cities={len(rows)}", flush=True); return 0


if __name__ == "__main__":
    raise SystemExit(run())
