from src.sources import (
    NEWS_QUERIES,
    is_iran_related,
    parse_google_news_rss,
    parse_tgju_overview,
    strip_html,
)


def test_strip_html():
    assert strip_html("<p>Hello <b>world</b><br>again</p>") == "Hello world again"


def test_iran_filter_accepts_iran_hormuz_and_rejects_unrelated():
    assert is_iran_related("Trump comments on Iran nuclear talks")
    assert is_iran_related("Two tankers pause near the Strait of Hormuz")
    assert is_iran_related("قالیباف درباره ایران و مذاکرات گفت")
    assert not is_iran_related("Trump speaks about US interest rates")
    assert not is_iran_related("Oil prices rise after OPEC meeting")


def test_major_foreign_iran_sources_are_configured():
    names = {name for name, _, _ in NEWS_QUERIES}
    expected = {
        "Reuters",
        "Associated Press",
        "BBC News",
        "CNN",
        "Financial Times",
        "The New York Times",
        "France 24",
        "DW",
        "Times of Israel",
        "Haaretz",
    }
    assert expected <= names


def test_parse_google_news_rss_filters_irrelevant_and_labels_source():
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
      <item>
        <title>Trump discusses Iran talks - Axios</title>
        <link>https://news.google.com/a</link>
        <guid>ga</guid>
        <pubDate>Fri, 04 Sep 2026 10:00:00 GMT</pubDate>
        <description><![CDATA[<p>New comments on Iran and Hormuz.</p>]]></description>
        <source url="https://axios.com">Axios</source>
      </item>
      <item>
        <title>Trump talks about tax policy - Axios</title>
        <link>https://news.google.com/b</link>
        <guid>gb</guid>
        <pubDate>Fri, 04 Sep 2026 11:00:00 GMT</pubDate>
        <description><![CDATA[<p>US domestic policy.</p>]]></description>
        <source url="https://axios.com">Axios</source>
      </item>
    </channel></rss>'''
    items = parse_google_news_rss(xml, fallback_source="Axios")
    assert len(items) == 1
    assert items[0].source == "Axios"
    assert items[0].title.startswith("Trump discusses Iran talks")
    assert items[0].key


def test_parse_tgju_market_overview_rial_and_toman():
    text = "بورس 6,503,971 (0%) طلا ۱۸ 228,351,000 (0%) دلار 2,199,000 (0%) یورو 2,561,300"
    snap = parse_tgju_overview(text)
    assert snap.usd_rial == 2_199_000
    assert snap.gold18_rial == 228_351_000
    assert snap.usd_toman == 219_900
    assert snap.gold18_toman == 22_835_100
