from src.editorial_rules import (
    editorial_detail,
    is_duplicate_story,
    is_low_value_company_news,
    is_priority_security_news,
    priority_search_queries,
)
from src.sources import NewsItem


def _item(key, source, title, summary=""):
    return NewsItem(key, source, title, summary, f"https://example.com/{key}", "Fri, 04 Sep 2026 20:00:00 GMT")


def test_same_event_from_different_outlets_is_duplicate_even_with_reworded_headline():
    original = _item(
        "toi-plan",
        "Times of Israel",
        "US drafting post-war plan to build alliance against Iran and expand Abraham Accords",
        "Washington is preparing a plan for after the war that would form a regional coalition against Iran and broaden the Abraham Accords.",
    )
    duplicate = _item(
        "reuters-plan",
        "Reuters",
        "Washington works on postwar regional coalition against Iran, wider Abraham Accords",
        "The United States is drawing up a postwar framework for an anti-Iran regional alliance and expansion of the Abraham Accords.",
    )
    assert is_duplicate_story(original, duplicate)


def test_same_intelligence_claim_republished_by_another_outlet_is_duplicate():
    original = _item(
        "nyt-intel",
        "The New York Times",
        "US intelligence believes Iran wants to escalate war before midterm elections",
        "American intelligence assesses that Tehran may intensify the conflict before the US midterm elections.",
    )
    duplicate = _item(
        "haaretz-intel",
        "Haaretz",
        "Haaretz cites NYT: US intel says Iran seeks escalation ahead of midterms",
        "The assessment says Iran wants to intensify the war before the midterm vote.",
    )
    assert is_duplicate_story(original, duplicate)


def test_distinct_development_on_same_broad_topic_is_not_duplicate():
    old = _item(
        "talks",
        "Reuters",
        "US and Iran discuss possible negotiations after the war",
        "Officials discussed whether talks could resume.",
    )
    new = _item(
        "sanctions",
        "BBC News",
        "US imposes new sanctions on Iranian oil exports",
        "A new sanctions package targets several oil export networks.",
    )
    assert not is_duplicate_story(old, new)


def test_low_value_company_performance_story_is_filtered_even_when_war_is_context():
    item = _item(
        "etihad-profit",
        "Reuters",
        "Etihad CEO says Iran war dents record profit run but expansion continues",
        "The airline plans to keep adding aircraft and routes despite pressure on earnings from the Iran war.",
    )
    assert is_low_value_company_news(item)


def test_company_story_with_direct_operational_security_impact_is_kept():
    item = _item(
        "airline-suspends",
        "Reuters",
        "Airline suspends Tehran flights after airspace closure",
        "The carrier cancelled flights after authorities closed Iranian airspace following missile attacks.",
    )
    assert not is_low_value_company_news(item)


def test_editorial_detail_is_not_forced_to_two_sentences():
    detail = "نکته اول خبر. نکته دوم خبر. نکته سوم که برای فهم ماجرا لازم است. نکته چهارم تکمیلی."
    rendered = editorial_detail(detail)
    assert "نکته اول خبر." in rendered
    assert "نکته دوم خبر." in rendered
    assert "نکته سوم" in rendered
    assert "نکته چهارم" in rendered


def test_irgc_quds_force_and_mohsen_rezaei_are_priority_news():
    assert is_priority_security_news(_item(
        "irgc-lebanon", "The New York Times",
        "Iranian advisers trapped with Hezbollah fighters in southern Lebanon tunnels",
        "Members of the IRGC Quds Force are surrounded by Israeli troops.",
    ))
    assert is_priority_security_news(_item(
        "rezaei", "Reuters",
        "Mohsen Rezaei warns of a new phase in the Iran conflict",
    ))


def test_khatam_army_drones_and_missiles_are_priority_news():
    assert is_priority_security_news(_item(
        "khatam", "Reuters", "Khatam al-Anbiya commander issues statement on Iran defenses"
    ))
    assert is_priority_security_news(_item(
        "army", "BBC News", "Iranian Army announces new air-defense deployment"
    ))
    assert is_priority_security_news(_item(
        "missiles", "CNN", "Iran moves ballistic and cruise missiles as drone units prepare"
    ))


def test_energy_infrastructure_threats_and_netanyahu_katz_iran_statements_are_priority():
    assert is_priority_security_news(_item(
        "energy", "Times of Israel",
        "Israel threatens strikes on Iran energy infrastructure if attacks resume",
    ))
    assert is_priority_security_news(_item(
        "netanyahu", "Reuters", "Netanyahu says Israel will respond to any new Iranian attack"
    ))
    assert is_priority_security_news(_item(
        "katz", "Reuters", "Israel Katz warns Iran over missile attacks"
    ))


def test_priority_queries_explicitly_monitor_required_people_and_capabilities():
    query_text = " ".join(query for _, query in priority_search_queries()).lower()
    for term in (
        "netanyahu", "israel katz", "mohsen rezaei", "irgc", "quds force",
        "khatam al-anbiya", "iranian army", "ballistic missile", "cruise missile",
        "drone", "energy infrastructure",
    ):
        assert term in query_text
