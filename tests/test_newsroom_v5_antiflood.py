from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.newsroom_v5_antiflood import AutoPublishPacer


def test_pacer_serializes_bursts_without_dropping_story():
    pacer = AutoPublishPacer(min_interval_seconds=30)
    now = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
    first = pacer.decide(now=now, last_publish_at=None)
    second = pacer.decide(now=now + timedelta(seconds=5), last_publish_at=now)
    assert first.allow is True
    assert second.allow is False
    assert second.route == "review"
    assert second.retry_after_seconds == 25


def test_legacy_daily_limit_routes_candidate_to_review_not_discard():
    pacer = AutoPublishPacer(min_interval_seconds=0)
    decision = pacer.decide(now=datetime.now(timezone.utc), last_publish_at=None, daily_limit_reached=True)
    assert decision.allow is False
    assert decision.route == "review"
    assert decision.reason == "daily_limit_reached"
