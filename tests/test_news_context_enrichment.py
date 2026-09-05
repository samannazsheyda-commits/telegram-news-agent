from datetime import datetime, timezone

import src.runtime_v2 as runtime
from src.news_context import fetch_news_detail_enriched
from src.sources import NewsItem


class _Response:
    def __init__(self, html):
        self.text = html

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, html):
        self.html = html

    def get(self, *args, **kwargs):
        return _Response(self.html)


def test_detail_combines_subheadline_with_body_fact_needed_to_answer_where():
    item = NewsItem(
        "irgc-west",
        "Al Arabiya",
        "IRGC says four personnel killed in US attack in western province",
        "Iran's Revolutionary Guards said four personnel were killed in a US strike in a western province.",
        "https://example.com/irgc",
        "Tue, 02 Sep 2026 08:46:00 GMT",
    )
    html = """
    <html><head>
      <meta property="og:description" content="Iran's Revolutionary Guards said four personnel were killed in a US strike in a western province.">
    </head><body>
      <p>The Guards identified the location as Kermanshah province in western Iran.</p>
      <p>The statement said the four were members of the force stationed in the province.</p>
    </body></html>
    """
    detail = fetch_news_detail_enriched(item, session=_Session(html))
    assert "western province" in detail
    assert "Kermanshah province" in detail


def test_detail_keeps_multiple_nonredundant_explanatory_facts_for_context_heavy_story():
    item = NewsItem(
        "kuwait-iranians",
        "France 24",
        "Iranians in Kuwait under pressure since war began",
        "Iranian residents in Kuwait say the war has changed their daily lives.",
        "https://example.com/kuwait",
        "Wed, 03 Sep 2026 10:41:00 GMT",
    )
    html = """
    <html><head>
      <meta name="description" content="Iranian residents in Kuwait say the war has changed their daily lives.">
    </head><body>
      <p>Some residents described increased scrutiny and anxiety over their legal status and travel.</p>
      <p>Community members said they were trying to avoid political discussions and keep a low profile.</p>
    </body></html>
    """
    detail = fetch_news_detail_enriched(item, session=_Session(html))
    assert "increased scrutiny" in detail
    assert "legal status and travel" in detail
    assert "avoid political discussions" in detail


def test_detail_keeps_evidence_and_claim_context_for_disputed_attack_story():
    item = NewsItem(
        "wedding-attack",
        "France 24",
        "Videos and debris raise questions about alleged US strike on Iranian wedding",
        "Visual evidence has prompted questions about what happened at the wedding site.",
        "https://example.com/wedding",
        "Tue, 02 Sep 2026 17:31:00 GMT",
    )
    html = """
    <html><head>
      <meta name="description" content="Visual evidence has prompted questions about what happened at the wedding site.">
    </head><body>
      <p>France 24 reviewed videos from the scene and images of debris recovered after the blast.</p>
      <p>The material was compared with the public claims made about the alleged US strike.</p>
    </body></html>
    """
    detail = fetch_news_detail_enriched(item, session=_Session(html))
    assert "reviewed videos from the scene" in detail
    assert "images of debris" in detail
    assert "public claims" in detail


def test_priority_news_from_two_days_ago_is_not_republished_as_fresh_news():
    item = NewsItem(
        "old-notam",
        "NOTAM / Airspace",
        "Bahrain, Kuwait and Jordan intercept Iranian missile and drone attacks",
        "Iranian missiles and drones were intercepted by regional states.",
        "https://example.com/old-notam",
        "Wed, 02 Sep 2026 07:10:00 GMT",
    )
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    assert runtime._strict_rejection_reason(item, now) == "not_today_tehran"
