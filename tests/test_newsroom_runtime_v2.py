from datetime import datetime, timezone

from src.newsroom_models import RawNewsItem
from src.newsroom_runtime_v2 import run_once


def _fresh():
    return RawNewsItem(
        source="Reuters",
        source_url="https://example.com/fresh",
        source_item_id="fresh-1",
        published_at="2026-09-07T21:00:00+00:00",
        fetched_at="2026-09-07T21:01:00+00:00",
        title="Iran launches ballistic missiles toward Israel",
    )


def test_shadow_run_never_calls_real_publisher(tmp_path):
    calls = []
    result = run_once(
        shadow=True,
        fetchers=[lambda: [_fresh()]],
        publisher=lambda item: calls.append(item) or {"ok": True, "message_id": 1},
        data_dir=tmp_path,
        now=datetime(2026, 9, 7, 21, 30, tzinfo=timezone.utc),
    )
    assert calls == []
    assert result["telegram_writes"] == 0
    assert result["panel_feed_count"] == 1


def test_production_run_uses_verified_publisher(tmp_path):
    calls = []
    result = run_once(
        shadow=False,
        fetchers=[lambda: [_fresh()]],
        publisher=lambda item: calls.append(item.raw.source_item_id) or {"ok": True, "message_id": 55},
        data_dir=tmp_path,
        now=datetime(2026, 9, 7, 21, 30, tzinfo=timezone.utc),
    )
    assert calls == ["fresh-1"]
    assert result["published"] == 1
    assert result["telegram_writes"] == 1
