from pathlib import Path

from src.local_json_repository import LocalJsonRepository, LocalWriteConflict
from src.weather_digest import format_digest


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


def test_weather_digest_is_short_technical_and_has_required_metrics():
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
    assert "🌧️ 55٪ (1.8 mm)" in text
    assert "💨 22/39 km/h" in text
    assert "https://open-meteo.com/" in text
    assert "محاوره" not in text


def test_weather_digest_uses_readable_two_line_city_blocks_with_blank_spacing():
    text = format_digest([
        {
            "name": "تهران", "date": "2026-09-09", "code": 2,
            "tmax": 32, "tmin": 20, "humidity": 40,
            "pop": 0, "precip": 0.0, "wind": 11, "gust": 30,
        },
        {
            "name": "کرج", "date": "2026-09-09", "code": 3,
            "tmax": 30, "tmin": 14, "humidity": 57,
            "pop": 3, "precip": 0.0, "wind": 18, "gust": 44,
        },
    ])
    assert "⛅ تهران — نیمه‌ابری\n🌡️ 20 تا 32°C" in text
    assert "☁️ کرج — ابری\n🌡️ 14 تا 30°C" in text
    assert "💨 11/30 km/h\n\n☁️ کرج" in text
