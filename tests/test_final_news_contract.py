from __future__ import annotations

from datetime import datetime
from pathlib import Path

import src.newsroom_hybrid_runtime as hybrid
import src.newsroom_publisher as publisher_module
from src.newsroom_eligibility import evaluate_eligibility
from src.newsroom_normalize import normalize_item
from src.newsroom_publisher import TelegramNewsroomPublisher
from src.newsroom_models import RawNewsItem

NOW = datetime.fromisoformat("2026-09-09T19:30:00+00:00")


def _raw(title: str, summary: str = "", *, source: str = "Reuters", priority: str = "normal") -> RawNewsItem:
    return RawNewsItem(
        source=source,
        source_url="https://example.com/story",
        source_item_id="story-1",
        published_at="2026-09-09T19:20:00+00:00",
        fetched_at="2026-09-09T19:21:00+00:00",
        title=title,
        summary=summary,
        source_priority=priority,
    )


def _eligible(title: str, summary: str = "", *, source: str = "Reuters", priority: str = "normal"):
    return evaluate_eligibility(normalize_item(_raw(title, summary, source=source, priority=priority)), NOW)


def test_only_user_requested_news_topics_are_auto_publishable():
    allowed = (
        "Iran launches ballistic missiles toward Israel",
        "Missile attack targets Iran overnight",
        "Explosion reported at a military site in Tehran",
        "Iranian forces attack a military target in the Gulf",
        "Tanker struck near the Strait of Hormuz",
        "New sanctions imposed on Iran shipping network",
        "Iran-linked cargo ship seized in the Gulf",
        "Dollar exchange rate rises against the Iranian rial",
        "Gold price rises sharply in Iran market",
    )
    for title in allowed:
        decision = _eligible(title)
        assert decision.eligible is True, (title, decision)


def test_unrelated_iran_politics_airspace_and_generic_statements_are_hard_rejected_even_if_protected():
    rejected = (
        "Iran president meets parliament leaders in Tehran",
        "Iran reopens civilian airspace after routine review",
        "White House issues a new statement about Iran",
        "Iran tourism minister announces a new cultural program",
        "Trump says Iran should make a deal soon",
    )
    for title in rejected:
        decision = _eligible(title, source="White House", priority="protected")
        assert decision.eligible is False, (title, decision)
        assert decision.review is False, (title, decision)
        assert decision.reason == "filtered_outside_channel_scope"


def test_questions_analysis_opinion_and_explainers_never_publish_even_on_allowed_topics():
    for title in (
        "Could Iran close the Strait of Hormuz?",
        "Analysis: Why Iran's missile strategy is changing",
        "Explainer: What new Iran sanctions mean for shipping",
        "Opinion: Gold and dollar prices could surge after the war",
        "What we know about the explosion in Tehran",
    ):
        decision = _eligible(title)
        assert decision.eligible is False
        assert decision.review is False
        assert decision.reason == "filtered_question_or_article"


def test_publisher_fails_closed_when_translation_contains_visible_english(monkeypatch):
    item = normalize_item(_raw("BREAKING Iran launches missile toward Israel"))
    monkeypatch.setattr(publisher_module, "_lingva_translate", lambda text, session=None: "")
    publisher = TelegramNewsroomPublisher("token", "@channel", translator=lambda text: "حمله Iran با missile تایید شد")
    assert publisher._message(item) == ""


def test_unknown_source_never_leaks_latin_words_to_final_post():
    item = normalize_item(_raw("Iran launches a missile toward Israel", source="Some New Intel Desk / Telegram"))
    publisher = TelegramNewsroomPublisher("token", "@channel", translator=lambda text: "ایران یک موشک به سمت اسرائیل شلیک کرد")
    message = publisher._message(item)
    assert "Some" not in message
    assert "Intel" not in message
    assert "Telegram" not in message
    assert "منبع خبری / تلگرام" in message


def test_no_automatic_urgent_second_publisher_workflow_exists():
    assert not Path(".github/workflows/urgent-broadcast.yml").exists()


def test_runtime_has_singleton_guard_against_two_simultaneous_agents():
    assert hasattr(hybrid, "_acquire_singleton_lock")
