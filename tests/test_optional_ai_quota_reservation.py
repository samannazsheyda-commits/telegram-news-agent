from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.ai_newsroom import EditorialDecision
from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_live_feed import LiveFeedStore


NOW = datetime.fromisoformat("2026-09-13T07:30:00+00:00")


class CountingAI:
    available = True

    def __init__(self):
        self.config = SimpleNamespace(
            event_memory_hours=72,
            duplicate_threshold=0.87,
            importance_threshold=70,
            mode="optional",
        )
        self.score_calls = 0

    def embed_texts(self, texts):
        raise AssertionError("optional mode must reserve remote AI for publishing")

    def judge_relation(self, new_text, prior_text):
        raise AssertionError("optional mode must reserve remote AI for publishing")

    def score_story(self, text):
        self.score_calls += 1
        return EditorialDecision(
            importance=95,
            topic="security",
            publish=True,
            reason="would consume remote quota",
            new_fact=True,
            priority_class="critical",
        )


class Publisher:
    def __init__(self):
        self.items = []

    def __call__(self, item):
        self.items.append(item)
        return {"ok": True, "message_id": 4242}


def test_optional_mode_reserves_remote_ai_for_publish_stage(tmp_path):
    raw = RawNewsItem(
        source="Associated Press",
        source_url="https://ap.example/iran-missile",
        source_item_id="ap-1",
        published_at=(NOW - timedelta(minutes=2)).isoformat(),
        fetched_at=NOW.isoformat(),
        title="Iran launched ballistic missiles toward Israel overnight",
        summary="Iranian missiles were launched overnight, according to officials.",
        source_priority="normal",
    )
    ai = CountingAI()
    publisher = Publisher()
    summary = run_cycle(
        lambda: [raw],
        EventLedger(tmp_path / "events.json"),
        LiveFeedStore(tmp_path / "feed.json"),
        LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json"),
        publisher,
        {
            "auto_publish": True,
            "freshness_hours": 12,
            "panel_max_records": 500,
            "ai_newsroom_mode": "optional",
            "hourly_news_limit": 20,
        },
        NOW,
        ai=ai,
    )

    assert ai.score_calls == 0
    assert summary.published == 1
    assert len(publisher.items) == 1
