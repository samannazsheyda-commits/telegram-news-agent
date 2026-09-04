from src.main import is_important_news
from src.sources import (
    NEWS_QUERIES,
    SPECIAL_QUERIES,
    is_iran_related,
    is_security_alert,
    parse_google_news_rss,
    parse_tgju_overview,
    parse_tgju_profile_rate,
    parse_tgju_tether_rial,
    strip_html,
)


def test_strip_html():
    assert strip_html("<p>Hello <b>world</b><br>again</p>") == "Hello world again"


def test_iran_filter_accepts_iran_hormuz_and_rejects_unrelated():
    assert is_iran_related("Trump comments on Iran nuclear talks")
    assert is_iran_related("Two tankers pause near the Strait of Hormuz")
    assert is_iran_related("قالیباف درباره ایران و مذاکرات گفت")
    assert is_iran_related("Iran launched missiles toward Qatar")
    assert not is_iran_related("Trump speaks about US interest rates")
    assert not is_iran_related("Oil prices rise after OPEC meeting")


def test_security_alert_filter_for_tankers_and_airspace():
    assert is_security_alert("Explosion reported near tanker in Strait of Hormuz")
    assert is_security_alert("Iran airspace closed and flights cancelled after NOTAM")
    assert is_security_alert("EASA issues conflict-zone flight restriction for Persian Gulf")
    assert not is_security_alert("Routine tanker traffic update through Hormuz")
    assert not is_security_alert("Weekly airline schedule published")


def test_important_news_rejects_articles_analysis_and_vague_items():
    rejected = (
        "How can the US and Iran end their conflict? Three experts explain",
        "Why tensions between Iran and the United States continue",
        "What to know about Iran and the Strait of Hormuz",
        "Analysis: What Trump's Iran strategy could mean for the region",
        "Opinion: The case for a new Iran policy",
        "Trump may consider a new approach to Iran",
        "US officials are reviewing options on Iran",
        "Ruling expected soon over Trump's claims about the Strait of Hormuz",
    )
    for text in rejected:
        assert not is_important_news(text, "")


def test_important_news_accepts_clear_major_new_events():
    accepted = (
        "Iran launches missiles at US base in Qatar",
        "Qatar closes airspace after Iranian drone attack",
        "Trump announces new sanctions on Iran",
        "Iran and US suspend nuclear talks",
        "Tanker explodes near Strait of Hormuz",
        "Iran reopens airspace after NOTAM cancellation",
    )
    for text in accepted:
        assert is_important_news(text, "")


def test_special_monitors_are_configured():
    names = {name for name, _, _ in SPECIAL_QUERIES}
    expected = {
        "Barak Ravid / X",
        "Abbas Araghchi / X",
        "Mohsen Rezaei / X",
        "TankerTrackers",
        "NOTAM / Airspace",
        "Iran regional strikes",
    }
    assert expected <= names


def test_special_queries_keep_trump_truth_social_only():
    queries = {name: query for name, query, _ in SPECIAL_QUERIES}
    assert "truthsocial.com" in queries["Donald Trump / Truth Social"]
    assert "x.com" not in queries["Donald Trump / Truth Social"]


def test_major_foreign_iran_sources_are_configured():
    names = {name for name, _, _ in NEWS_QUERIES}
    expected = {
        "Reuters", "Associated Press", "BBC News", "CNN", "Financial Times",
        "The New York Times", "France 24", "DW", "Times of Israel", "Haaretz",
    }
    assert expected <= names


def test_parse_google_news_rss_filters_irrelevant_and_labels_source():
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
      <item>
        <title>Trump announces new Iran sanctions - Axios</title>
        <link>https://news.google.com/a</link>
        <guid>ga</guid>
        <pubDate>Fri, 04 Sep 2026 10:00:00 GMT</pubDate>
        <description><![CDATA[<p>The White House announced sanctions targeting Iran.</p>]]></description>
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
    assert items[0].title.startswith("Trump announces new Iran sanctions")
    assert items[0].published == "Fri, 04 Sep 2026 10:00:00 GMT"
    assert items[0].key


def test_parse_tgju_market_overview_rial_and_toman():
    text = (
        "بورس 6,503,971 (0%) طلا ۱۸ 228,351,000 (0%) سکه 2,279,900,000 (0%) "
        "دلار 2,199,000 (0%) یورو 2,561,300 (0%) بیت کوین 76,912.07 (0%)"
    )
    snap = parse_tgju_overview(text)
    assert snap.usd_rial == 2_199_000
    assert snap.gold18_rial == 228_351_000
    assert snap.eur_rial == 2_561_300
    assert snap.emami_rial == 2_279_900_000
    assert snap.bitcoin_usd == 76_912.07
    assert snap.usd_toman == 219_900
    assert snap.gold18_toman == 22_835_100


def test_parse_tgju_profile_and_tether_rial_prices():
    assert parse_tgju_profile_rate("پوند GBP نرخ فعلی:: 2,973,100 - ارز آزاد") == 2_973_100
    assert parse_tgju_tether_rial("نرخ فعلی 1.0 قیمت ریالی | 2,188,500 بالاترین") == 2_188_500
