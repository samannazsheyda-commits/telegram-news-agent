import src.sources as sources
from src.main import is_important_news
from src.sources import (
    NEWS_QUERIES,
    SPECIAL_QUERIES,
    is_iran_related,
    is_regional_security_alert,
    is_security_alert,
    parse_google_news_rss,
    parse_trumpstruth_rss,
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


def test_regional_security_alert_accepts_air_defense_without_explicit_iran_mention():
    assert is_regional_security_alert("Air defense activated in northern Jordan")
    assert is_regional_security_alert("Drone sirens sound in Qatar")
    assert is_regional_security_alert("Missile interception reported over Bahrain")
    assert not is_regional_security_alert("Jordan announces new tourism campaign")
    assert not is_regional_security_alert("Air defense exercise held in Poland")


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
        "Feature: Inside the debate over Iran policy",
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
        "US and allies seek UN Security Council action on Iran nuclear file",
        "Turkey sanctions bank over Iran-linked transactions",
        "Air defense activated in northern Jordan",
        "Drone sirens sound in Qatar",
    )
    for text in accepted:
        assert is_important_news(text, "")


def test_special_monitors_include_al_arabiya_regional_security_without_weak_pseudo_source():
    names = {name for name, _, _ in SPECIAL_QUERIES}
    expected = {
        "Donald Trump / Truth Social",
        "Barak Ravid / X",
        "Abbas Araghchi / X",
        "Mohsen Rezaei / X",
        "TankerTrackers",
        "NOTAM / Airspace",
        "Al Arabiya",
    }
    assert expected <= names
    assert "Iran regional strikes" not in names


def test_special_queries_keep_trump_truth_social_only():
    queries = {name: query for name, query, _ in SPECIAL_QUERIES}
    assert "truthsocial.com" in queries["Donald Trump / Truth Social"]
    assert "x.com" not in queries["Donald Trump / Truth Social"]


def test_major_foreign_iran_sources_are_configured():
    names = {name for name, _, _ in NEWS_QUERIES}
    expected = {
        "Reuters", "Associated Press", "BBC News", "CNN", "Financial Times",
        "The New York Times", "France 24", "DW", "Times of Israel", "Haaretz",
        "KAN 11", "N12", "Channel 13", "Fox News", "NBC News", "CBS News",
        "ABC News", "Sky News", "Bloomberg", "CNBC",
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


def test_parse_al_arabiya_regional_security_without_iran_word():
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item>
      <title>Air defense activated in northern Jordan - Al Arabiya English</title>
      <link>https://news.google.com/jordan-defense</link>
      <guid>ga</guid>
      <pubDate>Fri, 04 Sep 2026 16:30:00 GMT</pubDate>
      <description><![CDATA[<p>Air-defense systems were activated in northern Jordan.</p>]]></description>
      <source url="https://english.alarabiya.net">Al Arabiya English</source>
    </item></channel></rss>'''
    items = parse_google_news_rss(xml, fallback_source="Al Arabiya", allow_special_source=True)
    assert len(items) == 1
    assert items[0].source == "Al Arabiya"


def test_parse_trumpstruth_rss_builds_stable_posts():
    xml = b'''<?xml version="1.0"?><rss><channel><item>
      <title>Donald J. Trump: Iran must not threaten American forces</title>
      <link>https://www.trumpstruth.org/statuses/40123</link>
      <guid>https://www.trumpstruth.org/statuses/40123</guid>
      <pubDate>Fri, 04 Sep 2026 16:00:00 GMT</pubDate>
      <description><![CDATA[<p>Iran must not threaten American forces.</p>]]></description>
    </item></channel></rss>'''
    posts = parse_trumpstruth_rss(xml)
    assert len(posts) == 1
    assert posts[0].id == "40123"
    assert "Iran" in posts[0].text
    assert posts[0].url.endswith("/statuses/40123")


def test_fetch_news_items_skips_failed_source_and_keeps_other_sources(monkeypatch):
    good_xml = b'''<?xml version="1.0"?><rss><channel><item>
      <title>Iran launches missile at target - Reuters</title>
      <link>https://news.google.com/good</link>
      <pubDate>Fri, 04 Sep 2026 16:00:00 GMT</pubDate>
      <description>Iran missile attack confirmed.</description>
      <source>Reuters</source>
    </item></channel></rss>'''

    class Response:
        def __init__(self, content):
            self.content = content
        def raise_for_status(self):
            return None

    class Session:
        calls = 0
        @classmethod
        def get(cls, *args, **kwargs):
            cls.calls += 1
            if cls.calls == 1:
                raise RuntimeError("temporary source failure")
            return Response(good_xml if cls.calls == 2 else b'<rss><channel></channel></rss>')

    monkeypatch.setattr(sources, "NEWS_QUERIES", (("Axios", "q1", "en"), ("Reuters", "q2", "en")))
    monkeypatch.setattr(sources, "SPECIAL_QUERIES", ())
    items = sources.fetch_news_items(session=Session)
    assert len(items) == 1
    assert items[0].source == "Reuters"


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
