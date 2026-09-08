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
            "pop": 55,
            "precip": 1.8,
            "wind": 22,
            "gust": 39,
        }
    ])
    assert "تهران" in text
    assert "18 تا 27°C" in text
    assert "بارش 55٪ (1.8 mm)" in text
    assert "باد 22 km/h" in text
    assert "تندباد 39 km/h" in text
    assert "Open-Meteo" in text
    assert "محاوره" not in text
