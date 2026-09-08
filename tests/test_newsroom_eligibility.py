from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.newsroom_eligibility import evaluate_eligibility
from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item


def _raw(*, source="Reuters", title, summary="", published_at, priority="normal", source_url="https://example.com/story"):
    return RawNewsItem(
        source=source,
        source_url=source_url,
        source_item_id="id-1",
        published_at=published_at,
        fetched_at="2026-09-07T21:30:00+00:00",
        title=title,
        summary=summary,
        source_priority=priority,
    )


def _decision(raw, now="2026-09-07T21:30:00+00:00"):
    return evaluate_eligibility(normalize_item(raw), datetime.fromisoformat(now))


def test_current_centcom_operational_update_is_publishable():
    d = _decision(_raw(
        source="CENTCOM / X",
        title="CENTCOM says US forces redirected 92 commercial vessels, disabled 3 and boarded 2 near Iran",
        published_at="2026-09-07T21:10:00+00:00",
        priority="protected",
    ))
    assert d.eligible is True
    assert d.reason == "eligible"


def test_old_story_is_stale_and_not_publishable():
    d = _decision(_raw(
        title="Iran announces a new restricted maritime zone in the Gulf",
        published_at="2026-09-06T08:00:00+00:00",
    ))
    assert d.eligible is False
    assert d.reason == "stale"


def test_midnight_grace_allows_very_recent_previous_tehran_day():
    tehran = ZoneInfo("Asia/Tehran")
    now = datetime(2026, 9, 8, 0, 30, tzinfo=tehran)
    d = evaluate_eligibility(normalize_item(_raw(
        title="Iran partially reopens its airspace after a security closure",
        published_at="2026-09-07T20:15:00+00:00",
    )), now)
    assert d.eligible is True


def test_ordinary_company_earnings_story_is_filtered_low_value():
    d = _decision(_raw(
        title="Regional airline reports quarterly profit growth while monitoring Iran market",
        summary="The company raised its revenue outlook and discussed sales.",
        published_at="2026-09-07T20:45:00+00:00",
    ))
    assert d.eligible is False
    assert d.reason == "filtered_low_value"


def test_airline_resuming_iranian_overflights_is_operational_and_publishable():
    d = _decision(_raw(
        title="UAE airline resumes overflights through Iranian airspace after restrictions eased",
        published_at="2026-09-07T20:45:00+00:00",
    ))
    assert d.eligible is True


def test_current_irrelevant_story_is_not_publishable():
    d = _decision(_raw(
        title="European football club signs a new striker",
        published_at="2026-09-07T20:45:00+00:00",
    ))
    assert d.eligible is False
    assert d.reason == "not_iran_relevant"


def test_ambiguous_protected_story_goes_to_review_instead_of_silent_filter():
    d = _decision(_raw(
        source="White House",
        title="White House issues a new statement",
        summary="Officials said more details would follow.",
        published_at="2026-09-07T20:45:00+00:00",
        priority="protected",
    ))
    assert d.eligible is False
    assert d.reason == "needs_editorial_review"
    assert d.review is True


def test_invalid_publish_time_never_auto_publishes():
    d = _decision(_raw(
        title="Iran announces new airspace restrictions",
        published_at="not-a-date",
    ))
    assert d.eligible is False
    assert d.reason == "invalid_publish_time"


def test_question_headline_is_hard_filtered_even_from_protected_source():
    d = _decision(_raw(
        source="Reuters",
        title="Could Iran close the Strait of Hormuz?",
        published_at="2026-09-07T20:45:00+00:00",
        priority="protected",
    ))
    assert d.eligible is False
    assert d.reason == "filtered_question_or_article"
    assert d.review is False


def test_analysis_explainer_and_opinion_are_hard_filtered():
    for title in (
        "Analysis: What Iran's new missile posture means for the region",
        "Explainer: How sanctions could affect Iran's oil exports",
        "Opinion: Why Tehran may change its strategy",
        "What we know about Iran's latest military moves",
    ):
        d = _decision(_raw(title=title, published_at="2026-09-07T20:45:00+00:00"))
        assert d.eligible is False
        assert d.reason == "filtered_question_or_article"


def test_factual_breaking_headline_is_not_filtered_as_article():
    d = _decision(_raw(
        title="Explosion reported near Bandar Abbas port in Iran",
        published_at="2026-09-07T20:45:00+00:00",
    ))
    assert d.eligible is True


def test_malformed_domain_tail_summary_is_hard_filtered():
    d = _decision(_raw(
        source="Bloomberg",
        title="Iran seized an underwater drone that US forces say malfunctioned",
        summary="Iran seized an underwater drone that US forces say malfunctioned in Bloomberg.com.",
        published_at="2026-09-07T20:45:00+00:00",
        source_url="https://www.bloomberg.com/news/articles/example",
    ))
    assert d.eligible is False
    assert d.reason == "filtered_incomplete_or_teaser"


def test_teaser_and_truncated_content_never_auto_publishes():
    for summary in (
        "Read more at the original source",
        "Continue reading on Reuters.com",
        "Officials said the operation was ongoing…",
        "Officials said the operation was ongoing...",
    ):
        d = _decision(_raw(
            title="Iran announces a new maritime security operation in the Gulf",
            summary=summary,
            published_at="2026-09-07T20:45:00+00:00",
        ))
        assert d.eligible is False
        assert d.reason == "filtered_incomplete_or_teaser"


def test_aggregator_link_is_not_accepted_as_direct_source():
    d = _decision(_raw(
        title="Iran announces a new maritime security operation in the Gulf",
        summary="Officials said the operation began on Monday.",
        published_at="2026-09-07T20:45:00+00:00",
        source_url="https://news.google.com/rss/articles/example",
    ))
    assert d.eligible is False
    assert d.reason == "filtered_non_direct_source"


def test_ceremonial_condemnation_without_new_incident_is_low_value():
    d = _decision(_raw(
        source="Al Arabiya English / X",
        title="Saudi Crown Prince chairs cabinet session in Jeddah",
        summary="The cabinet condemned Iran-backed Houthi attacks on civilian sites in Abha, Khamis Mushait, Jazan and Najran.",
        published_at="2026-09-07T20:45:00+00:00",
    ))
    assert d.eligible is False
    assert d.reason == "filtered_low_value_reaction"


def test_high_value_war_sanctions_hormuz_and_maritime_events_pass():
    titles = (
        "Explosion reported at an Iranian military facility near Bandar Abbas",
        "US imposes new sanctions on Iran oil shipping network",
        "Iran closes part of the Strait of Hormuz after tanker incident",
        "Iranian forces seize tanker in the Persian Gulf",
        "Missile strike kills senior commander in Iran",
    )
    for title in titles:
        d = _decision(_raw(title=title, published_at="2026-09-07T20:45:00+00:00"))
        assert d.eligible is True, title


def test_generic_diplomatic_reaction_is_not_enough_for_panel_or_publish():
    d = _decision(_raw(
        title="Saudi officials condemn Iran-linked regional violence",
        summary="Officials reiterated concern during a government meeting.",
        published_at="2026-09-07T20:45:00+00:00",
    ))
    assert d.eligible is False
    assert d.reason == "filtered_low_value_reaction"
