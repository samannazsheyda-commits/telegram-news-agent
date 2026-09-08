from datetime import datetime, timezone

from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item
from src.newsroom_publisher import _breaking_prefix
from src.weather_digest import format_digest


def _normalized(title: str, summary: str = ""):
    raw = RawNewsItem(
        source="Reuters",
        source_url="https://example.com/story",
        source_item_id="id-1",
        published_at=datetime.now(timezone.utc).isoformat(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        title=title,
        summary=summary,
    )
    return normalize_item(raw)


def test_explosion_story_gets_explosion_breaking_prefix():
    assert _breaking_prefix(_normalized("Explosion reported near Bandar Abbas port in Iran")) == "💥 🔴 <b>خبر فوری</b>\n"


def test_non_explosion_story_does_not_get_explosion_prefix():
    assert _breaking_prefix(_normalized("Iran announces new shipping restrictions")) == ""


def test_weather_digest_is_readable_and_adds_only_useful_note():
    rows = [
        {"name": "تهران", "date": "2026-09-09", "code": 0, "tmin": 21, "tmax": 32, "humidity": 40, "pop": 0, "precip": 0.0, "wind": 18, "gust": 28},
        {"name": "اهواز", "date": "2026-09-09", "code": 0, "tmin": 29, "tmax": 45, "humidity": 38, "pop": 0, "precip": 0.0, "wind": 20, "gust": 31},
    ]
    text = format_digest(rows)
    assert "☀️ تهران — صاف\n🌡️ 21 تا 32°C" in text
    assert "☀️ اهواز — صاف\n🌡️ 29 تا 45°C" in text
    assert "\n\n☀️ اهواز" in text
    assert "توضیح:" in text
    assert "گرمای شدید" in text
    assert "https://open-meteo.com/" in text
