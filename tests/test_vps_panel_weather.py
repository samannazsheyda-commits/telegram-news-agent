from pathlib import Path

from src.local_json_repository import LocalJsonRepository, LocalWriteConflict
from src.weather_digest import CITIES, format_digest


def test_local_json_repository_reads_writes_and_detects_conflict(tmp_path: Path):
    repo = LocalJsonRepository(tmp_path)
    value, sha = repo.read_json("data/editorial_queue.json", [])
    assert value == []
    assert sha is None

    result = repo.write_json("data/editorial_queue.json", [{"id": "a"}], None, "write")
    assert result["sha"]
    value, current_sha = repo.read_json("data/editorial_queue.json", [])
    assert value == [{"id": "a"}]

    repo.write_json("data/editorial_queue.json", [{"id": "b"}], current_sha, "replace")
    try:
        repo.write_json("data/editorial_queue.json", [{"id": "c"}], current_sha, "stale")
    except LocalWriteConflict as exc:
        assert exc.response.status_code == 409
    else:
        raise AssertionError("stale local write must conflict")


def test_weather_city_list_includes_rasht():
    assert any(city[0] == "رشت" for city in CITIES)


def test_weather_digest_is_short_technical_and_has_required_metrics_without_mm():
    text = format_digest([
        {
            "name": "تهران",
            "date": "2026-09-09",
            "code": 61,
            "tmax": 27,
            "tmin": 18,
            "humidity": 41,
            "pop": 55,
            "precip": 1.8,
            "wind": 22,
            "gust": 39,
        }
    ])
    assert "تهران" in text
    assert "18 تا 27°C" in text
    assert "رطوبت 41٪" in text
    assert "🌧️ بارش 55٪" in text
    assert "💨 باد 22 km/h | تندباد 39 km/h" in text
    assert "mm" not in text
    assert "https://open-meteo.com/" in text
    assert "محاوره" not in text


def test_weather_digest_uses_three_line_city_blocks_with_blank_spacing():
    text = format_digest([
        {
            "name": "تهران", "date": "2026-09-09", "code": 2,
            "tmax": 32, "tmin": 20, "humidity": 40,
            "pop": 0, "precip": 0.0, "wind": 11, "gust": 30,
        },
        {
            "name": "رشت", "date": "2026-09-09", "code": 3,
            "tmax": 26, "tmin": 20, "humidity": 76,
            "pop": 20, "precip": 0.0, "wind": 14, "gust": 28,
        },
    ])
    assert "⛅ تهران — نیمه‌ابری\n🌡️ 20 تا 32°C | 💧 رطوبت 40٪\n🌧️ بارش 0٪ | 💨 باد 11 km/h | تندباد 30 km/h" in text
    assert "☁️ رشت — ابری\n🌡️ 20 تا 26°C | 💧 رطوبت 76٪\n🌧️ بارش 20٪ | 💨 باد 14 km/h | تندباد 28 km/h" in text
    assert "تندباد 30 km/h\n\n☁️ رشت" in text
