from src.newsroom_fingerprint import build_fingerprint
from src.newsroom_models import NormalizedNewsItem, RawNewsItem
from src.realtime_search import _fresh_query


def _item(published_at: str, text: str) -> NormalizedNewsItem:
    raw = RawNewsItem(
        source="Test",
        source_url="https://example.com/x",
        source_item_id=published_at,
        published_at=published_at,
        fetched_at=published_at,
        title=text,
    )
    return NormalizedNewsItem(
        raw=raw,
        actors=["iran"],
        locations=["israel"],
        actions=["launch"],
        objects=["missiles"],
        numeric_facts=[],
        topic_tags=[],
        quoted_speaker="",
        normalized_text=text.lower(),
    )


def test_breaking_events_use_30_minute_time_buckets():
    first = build_fingerprint(_item("2026-09-09T10:05:00+00:00", "Iran launches missiles toward Israel"))
    same_window = build_fingerprint(_item("2026-09-09T10:25:00+00:00", "Iran launches missiles toward Israel"))
    later_wave = build_fingerprint(_item("2026-09-09T10:35:00+00:00", "Iran launches missiles toward Israel"))
    assert first.time_bucket == "2026-09-09T10:00Z"
    assert same_window.time_bucket == first.time_bucket
    assert later_wave.time_bucket == "2026-09-09T10:30Z"
    assert later_wave.key != first.key


def test_non_breaking_items_keep_daily_bucket():
    item = _item("2026-09-09T10:35:00+00:00", "Iran announces a diplomatic meeting")
    item = NormalizedNewsItem(
        raw=item.raw,
        actors=item.actors,
        locations=item.locations,
        actions=["announce"],
        objects=["meeting"],
        numeric_facts=[],
        topic_tags=[],
        quoted_speaker="",
        normalized_text="iran announces a diplomatic meeting",
    )
    assert build_fingerprint(item).time_bucket == "2026-09-09"


def test_google_fallback_queries_are_constrained_to_last_hour():
    assert _fresh_query('Iran missile') == 'Iran missile when:1h'
    assert _fresh_query('Iran missile when:30m') == 'Iran missile when:30m'
