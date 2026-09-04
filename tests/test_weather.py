from src.weather import (
    PROVINCIAL_CAPITALS,
    format_night_weather,
    format_noon_weather,
    parse_weather_payload,
    weather_code_fa,
)


def _row(temp=25, code=0):
    return {
        "current": {
            "temperature_2m": temp,
            "apparent_temperature": temp - 1,
            "weather_code": code,
            "wind_speed_10m": 12,
        },
        "daily": {
            "time": ["2026-09-04", "2026-09-05", "2026-09-06", "2026-09-07"],
            "weather_code": [code, 61, 3, 0],
            "temperature_2m_min": [15, 14, 13, 12],
            "temperature_2m_max": [27, 26, 25, 24],
            "precipitation_probability_max": [10, 80, 30, 0],
            "precipitation_sum": [0, 12, 1, 0],
            "snowfall_sum": [0, 0, 0, 0],
            "wind_gusts_10m_max": [20, 30, 25, 15],
        },
    }


def test_all_31_provincial_capitals_are_unique():
    assert len(PROVINCIAL_CAPITALS) == 31
    assert len({x[0] for x in PROVINCIAL_CAPITALS}) == 31
    assert len({x[1] for x in PROVINCIAL_CAPITALS}) == 31


def test_weather_code_labels_cover_major_conditions():
    assert weather_code_fa(0) == "صاف"
    assert weather_code_fa(61) == "بارانی"
    assert weather_code_fa(71) == "برفی"
    assert weather_code_fa(95) == "رعدوبرق"


def test_parse_and_format_31_city_weather_with_source():
    report = parse_weather_payload([_row() for _ in PROVINCIAL_CAPITALS])
    assert len(report.cities) == 31
    noon = format_noon_weather(report)
    night = format_night_weather(report)
    assert "تهران" in noon and "بندرعباس" in noon
    assert "پیش‌بینی هوای فردا" in night
    assert "بارش ۸۰٪" in night
    assert "Open-Meteo" in noon and "Open-Meteo" in night
    assert "مراکز ۳۱ استان" in noon and "مراکز ۳۱ استان" in night
