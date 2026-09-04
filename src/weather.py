from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_SOURCE = "https://open-meteo.com/"
TEHRAN = ZoneInfo("Asia/Tehran")
CHANNEL_URL = "https://t.me/bikhabaar"

# province, capital, latitude, longitude
PROVINCIAL_CAPITALS: tuple[tuple[str, str, float, float], ...] = (
    ("آذربایجان شرقی", "تبریز", 38.0800, 46.2919),
    ("آذربایجان غربی", "ارومیه", 37.5527, 45.0761),
    ("اردبیل", "اردبیل", 38.2498, 48.2933),
    ("اصفهان", "اصفهان", 32.6546, 51.6680),
    ("البرز", "کرج", 35.8400, 50.9391),
    ("ایلام", "ایلام", 33.6374, 46.4227),
    ("بوشهر", "بوشهر", 28.9234, 50.8203),
    ("تهران", "تهران", 35.6892, 51.3890),
    ("چهارمحال و بختیاری", "شهرکرد", 32.3256, 50.8644),
    ("خراسان جنوبی", "بیرجند", 32.8663, 59.2211),
    ("خراسان رضوی", "مشهد", 36.2605, 59.6168),
    ("خراسان شمالی", "بجنورد", 37.4747, 57.3290),
    ("خوزستان", "اهواز", 31.3183, 48.6706),
    ("زنجان", "زنجان", 36.6736, 48.4787),
    ("سمنان", "سمنان", 35.5769, 53.3921),
    ("سیستان و بلوچستان", "زاهدان", 29.4963, 60.8629),
    ("فارس", "شیراز", 29.5918, 52.5837),
    ("قزوین", "قزوین", 36.2688, 50.0041),
    ("قم", "قم", 34.6416, 50.8746),
    ("کردستان", "سنندج", 35.3219, 46.9862),
    ("کرمان", "کرمان", 30.2839, 57.0834),
    ("کرمانشاه", "کرمانشاه", 34.3142, 47.0650),
    ("کهگیلویه و بویراحمد", "یاسوج", 30.6682, 51.5879),
    ("گلستان", "گرگان", 36.8456, 54.4393),
    ("گیلان", "رشت", 37.2808, 49.5832),
    ("لرستان", "خرم‌آباد", 33.4878, 48.3558),
    ("مازندران", "ساری", 36.5633, 53.0601),
    ("مرکزی", "اراک", 34.0917, 49.6892),
    ("هرمزگان", "بندرعباس", 27.1832, 56.2666),
    ("همدان", "همدان", 34.7992, 48.5146),
    ("یزد", "یزد", 31.8974, 54.3569),
)


@dataclass(frozen=True)
class WeatherDay:
    date: str
    code: int | None
    temp_min: float | None
    temp_max: float | None
    precipitation_probability: float | None
    precipitation_sum: float | None
    snowfall_sum: float | None
    wind_gust_max: float | None


@dataclass(frozen=True)
class WeatherCity:
    province: str
    city: str
    current_temp: float | None
    apparent_temp: float | None
    current_code: int | None
    wind_speed: float | None
    days: tuple[WeatherDay, ...]


@dataclass(frozen=True)
class WeatherReport:
    generated_at: datetime
    cities: tuple[WeatherCity, ...]


def weather_code_fa(code: int | None) -> str:
    if code is None:
        return "نامشخص"
    if code == 0:
        return "صاف"
    if code in {1, 2}:
        return "کمی ابری"
    if code == 3:
        return "ابری"
    if code in {45, 48}:
        return "مه‌آلود"
    if code in {51, 53, 55, 56, 57}:
        return "نم‌نم باران"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "بارانی"
    if code in {71, 73, 75, 77, 85, 86}:
        return "برفی"
    if code in {95, 96, 99}:
        return "رعدوبرق"
    return "متغیر"


def _to_persian_digits(value: str) -> str:
    return value.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _num(values, index: int):
    if not isinstance(values, list) or index >= len(values):
        return None
    value = values[index]
    return None if value is None else float(value)


def _code(values, index: int):
    value = _num(values, index)
    return None if value is None else int(value)


def parse_weather_payload(payload) -> WeatherReport:
    rows = payload if isinstance(payload, list) else [payload]
    if len(rows) != len(PROVINCIAL_CAPITALS):
        raise ValueError(f"expected {len(PROVINCIAL_CAPITALS)} weather locations, got {len(rows)}")
    cities: list[WeatherCity] = []
    for meta, row in zip(PROVINCIAL_CAPITALS, rows):
        province, city, _, _ = meta
        current = row.get("current") or {}
        daily = row.get("daily") or {}
        dates = daily.get("time") or []
        days: list[WeatherDay] = []
        for i, date in enumerate(dates[:4]):
            days.append(WeatherDay(
                str(date),
                _code(daily.get("weather_code"), i),
                _num(daily.get("temperature_2m_min"), i),
                _num(daily.get("temperature_2m_max"), i),
                _num(daily.get("precipitation_probability_max"), i),
                _num(daily.get("precipitation_sum"), i),
                _num(daily.get("snowfall_sum"), i),
                _num(daily.get("wind_gusts_10m_max"), i),
            ))
        cities.append(WeatherCity(
            province,
            city,
            None if current.get("temperature_2m") is None else float(current["temperature_2m"]),
            None if current.get("apparent_temperature") is None else float(current["apparent_temperature"]),
            None if current.get("weather_code") is None else int(current["weather_code"]),
            None if current.get("wind_speed_10m") is None else float(current["wind_speed_10m"]),
            tuple(days),
        ))
    return WeatherReport(datetime.now(timezone.utc), tuple(cities))


def fetch_weather_report(session=requests) -> WeatherReport:
    params = {
        "latitude": ",".join(str(x[2]) for x in PROVINCIAL_CAPITALS),
        "longitude": ",".join(str(x[3]) for x in PROVINCIAL_CAPITALS),
        "timezone": "Asia/Tehran",
        "forecast_days": 4,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,snowfall_sum,weather_code,wind_gusts_10m_max",
    }
    response = session.get(OPEN_METEO_URL, params=params, timeout=30, headers={"User-Agent": "TelegramNewsAgent/2.0"})
    response.raise_for_status()
    return parse_weather_payload(response.json())


def _fmt_temp(value: float | None) -> str:
    return "—" if value is None else f"{round(value):+d}°"


def _fmt_plain_number(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = round(value, 1)
    if rounded.is_integer():
        return _to_persian_digits(str(int(rounded)))
    return _to_persian_digits(str(rounded).replace(".", "٫"))


def _important_weather_notes(report: WeatherReport, day_index: int) -> list[str]:
    notes: list[str] = []
    for city in report.cities:
        if day_index >= len(city.days):
            continue
        day = city.days[day_index]
        if (day.precipitation_probability or 0) >= 80 and (day.precipitation_sum or 0) >= 10:
            notes.append(f"بارش قابل‌توجه در {city.city}")
        if (day.snowfall_sum or 0) >= 2:
            notes.append(f"احتمال برف در {city.city}")
        if (day.wind_gust_max or 0) >= 60:
            notes.append(f"تندباد در {city.city}")
        if (day.temp_max or -100) >= 42:
            notes.append(f"گرمای شدید در {city.city}")
        if (day.temp_min or 100) <= -8:
            notes.append(f"سرمای شدید در {city.city}")
    return notes[:6]


def _footer() -> str:
    return f'\n📌 <a href="{OPEN_METEO_SOURCE}">منبع داده: Open-Meteo</a>\n\n📡 <a href="{CHANNEL_URL}">بی‌خبر</a> ←\nمانیتور تحولات ایران'


def format_noon_weather(report: WeatherReport) -> str:
    lines = ["🌡 <b>دمای امروز مراکز ۳۱ استان</b>"]
    for city in report.cities:
        lines += ["", f"▫️ <b>{escape(city.city)}</b>: {_fmt_temp(city.current_temp)} — {weather_code_fa(city.current_code)}"]
    lines.append(_footer())
    return "\n".join(lines)


def _conversational_forecast(city: WeatherCity, day: WeatherDay) -> str:
    parts = [
        f"فردا {escape(city.city)} هوا {weather_code_fa(day.code)}ه و دما بین {_fmt_temp(day.temp_min)} تا {_fmt_temp(day.temp_max)} می‌مونه"
    ]
    if day.precipitation_probability is not None:
        parts.append(f"احتمال بارش {_to_persian_digits(str(round(day.precipitation_probability)))}٪ه")
    if (day.precipitation_sum or 0) > 0:
        parts.append(f"حدود {_fmt_plain_number(day.precipitation_sum)} میلی‌متر بارش داریم")
    if (day.snowfall_sum or 0) > 0:
        parts.append(f"برف تجمعی حدود {_fmt_plain_number(day.snowfall_sum)} سانتی‌متره")
    if (day.wind_gust_max or 0) >= 45:
        parts.append(f"تندباد هم ممکنه تا {_fmt_plain_number(day.wind_gust_max)} کیلومتر بر ساعت برسه")
    return "؛ ".join(parts) + "."


def format_night_weather(report: WeatherReport) -> str:
    lines = ["🌙 <b>پیش‌بینی دقیق هوای فردا | مراکز ۳۱ استان</b>"]
    notes = _important_weather_notes(report, 1)
    if notes:
        lines += ["", "⚠️ <b>نکته‌های مهم فردا:</b> " + "؛ ".join(escape(x) for x in notes)]
    for city in report.cities:
        if len(city.days) < 2:
            continue
        lines += ["", f"▫️ <b>{escape(city.city)}</b>: {_conversational_forecast(city, city.days[1])}"]
    lines.append(_footer())
    return "\n".join(lines)
