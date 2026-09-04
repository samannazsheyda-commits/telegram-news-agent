# Iran Weather Reports Design

## Goal

Add two scheduled Iran-wide weather posts to the Telegram news agent, covering the capital city of all 31 provinces.

## Schedule

- 12:00 Asia/Tehran: current conditions report for all 31 provincial capitals.
- 22:00 Asia/Tehran: tomorrow forecast plus a compact 3-day outlook for all 31 provincial capitals.
- Each report is sent at most once per Tehran calendar day even though the monitor polls every minute.

## Data source

Use Open-Meteo's public forecast API with no API key. Batch all 31 coordinates in one request where practical. Use `timezone=Asia/Tehran` and request current temperature, apparent temperature, weather code, wind speed, plus daily minimum/maximum temperature, precipitation probability maximum, precipitation sum, snowfall sum, weather code, and wind-gust maximum for forecast days.

No weather fact may be invented. If the weather API fails or returns incomplete data, skip the affected report rather than fabricating values.

## Locations

Cover one city per province: Tehran, Mashhad, Isfahan, Shiraz, Tabriz, Ahvaz, Qom, Karaj, Rasht, Sari, Gorgan, Ardabil, Urmia, Sanandaj, Kermanshah, Ilam, Khorramabad, Hamedan, Arak, Qazvin, Zanjan, Semnan, Birjand, Bojnord, Kerman, Yazd, Zahedan, Bandar Abbas, Bushehr, Yasuj, Shahrekord.

Coordinates are stored in code as fixed WGS84 values so the agent does not depend on a separate geocoding service.

## Noon post

Header: `🌤 وضعیت هوای ایران | امروز`

For each provincial capital show a compact one-line current condition with city, temperature, weather description, and wind when useful. Keep the entire post readable in Telegram by grouping cities into short lines and avoiding verbose prose.

## Night post

Header: `🌙 پیش‌بینی هوای ایران | فردا`

For each provincial capital show tomorrow's max/min temperature, weather description, and maximum precipitation probability. Then append a compact `🔭 چشم‌انداز ۳ روزه` section summarizing notable patterns using deterministic rules based on the returned data, not generated speculation.

## Alerts

Surface a short alert block when returned forecast data crosses clear thresholds:

- heavy precipitation: daily precipitation >= 20 mm or precipitation probability >= 80% with precipitation >= 10 mm;
- snow: daily snowfall >= 2 cm;
- strong wind: daily max gust >= 60 km/h;
- heat: daily max temperature >= 40°C;
- cold: daily min temperature <= -5°C.

Alerts are data-derived and should name the affected cities. Do not describe these as official government warnings.

## State

Persist two state keys:

- `weather_noon_last_sent_date`
- `weather_night_last_sent_date`

Use Tehran date strings (`YYYY-MM-DD`) and only mark a report sent after Telegram delivery succeeds.

## Failure isolation

Weather failures must never stop news, Truth Social, or market processing. The weather section gets its own exception handling.

## Verification

Tests must cover:

- exactly 31 configured provincial capitals;
- Open-Meteo payload parsing;
- WMO weather-code Persian labels;
- noon report due once at/after 12:00 Tehran and not twice on the same date;
- night report due once at/after 22:00 Tehran and not twice on the same date;
- forecast formatting for all 31 capitals;
- threshold alerts;
- weather API failure does not crash the agent;
- existing market quiet-hours and news behavior remain unchanged.
