from datetime import datetime

from src.newsroom_eligibility import evaluate_eligibility
from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item


NOW = datetime.fromisoformat("2026-09-12T21:05:00+00:00")
GOOGLE_RSS_URL = "https://news.google.com/rss/articles/example"


def _decision(source: str):
    raw = RawNewsItem(
        source=source,
        source_url=GOOGLE_RSS_URL,
        source_item_id="google-rss-1",
        published_at="2026-09-12T20:55:00+00:00",
        fetched_at="2026-09-12T21:05:00+00:00",
        title="Iran announces new airspace restrictions after missile attack",
        summary="Authorities issued a new NOTAM after the attack.",
        source_priority="normal",
    )
    return evaluate_eligibility(normalize_item(raw), NOW)


def test_fresh_google_news_item_from_approved_publisher_is_eligible():
    decision = _decision("Reuters")
    assert decision.eligible is True
    assert decision.reason == "eligible"


def test_google_news_item_from_unapproved_source_remains_blocked():
    decision = _decision("Unknown Blog")
    assert decision.eligible is False
    assert decision.reason == "filtered_non_direct_source"
