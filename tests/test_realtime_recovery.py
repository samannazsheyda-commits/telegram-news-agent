from datetime import datetime, timezone
from pathlib import Path

from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_raw_intake import build_raw_fetchers
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore
from src.sources import NewsItem
from src.weather_digest import build_preview


NOW = datetime(2026, 9, 9, 10, 30, tzinfo=timezone.utc)


def _raw(item_id: str, published: str) -> RawNewsItem:
    return RawNewsItem(
        source="Direct Test",
        source_url=f"https://example.com/{item_id}",
        source_item_id=item_id,
        published_at=published,
        fetched_at=NOW.isoformat(),
        title="Iran launches ballistic missile during new attack",
        summary="A direct operational update.",
    )


def test_raw_intake_has_dedicated_direct_x_lane():
    calls = []

    def news(label):
        def fetch():
            calls.append(label)
            return [NewsItem(label, label, "Iran missile update", "", f"https://example.com/{label}", "Wed, 09 Sep 2026 10:20:00 +0000")]
        return fetch

    def truth():
        calls.append("truth")
        return []

    fetchers = build_raw_fetchers(
        direct_x_fetch=news("direct_x"),
        base_fetch=news("base"),
        custom_fetch=news("custom"),
        priority_fetch=news("priority"),
        truth_fetch=truth,
    )
    batches = [fetcher() for fetcher in fetchers]
    assert len(fetchers) == 5
    assert calls[0] == "direct_x"
    assert batches[0][0].source_item_id == "direct_x"


def test_stale_items_never_enter_ledger_or_live_feed(tmp_path: Path):
    ledger = EventLedger(tmp_path / "ledger.json")
    feed = LiveFeedStore(tmp_path / "live.json")
    editorial = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")
    stale = _raw("stale", "Mon, 16 Mar 2026 07:00:00 GMT")

    summary = run_cycle(
        fetcher=lambda: [stale],
        ledger=ledger,
        live_feed=feed,
        editorial_store=editorial,
        publisher=lambda item: (_ for _ in ()).throw(AssertionError("stale item must never publish")),
        settings={"auto_publish": True, "freshness_hours": 2},
        now=NOW,
    )

    assert summary.stale == 1
    assert ledger.records() == []
    assert feed.records() == []
    assert editorial.queue() == []


class _WeatherResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "daily": {
                "time": ["2026-09-09", "2026-09-10"],
                "weather_code": [0, 2],
                "temperature_2m_max": [30, 31],
                "temperature_2m_min": [20, 21],
                "precipitation_probability_max": [0, 15],
                "precipitation_sum": [0, 0],
                "wind_speed_10m_max": [10, 12],
                "wind_gusts_10m_max": [18, 24],
            },
            "hourly": {
                "time": ["2026-09-10T00:00", "2026-09-10T12:00"],
                "relative_humidity_2m": [40, 50],
            },
        }


class _WeatherSession:
    def get(self, *args, **kwargs):
        return _WeatherResponse()


def test_weather_preview_returns_exact_unsent_message():
    preview = build_preview(session=_WeatherSession())
    assert preview["message"].startswith("🌤️ پیش‌بینی هوای فردا")
    assert "تهران" in preview["message"]
    assert "رشت" in preview["message"]
    assert preview["source"] == "Open-Meteo"
    assert preview["city_count"] == 8
    assert preview["generated_at"]
