from src.editorial_rules import is_duplicate_story
from src.newsroom_x import builtin_x_news_sources, clean_x_post_text, resolve_x_post_url, x_monitor_query
from src.oil import OilSnapshot, format_oil_lines
from src.sources import MarketSnapshot, NewsItem
import src.runtime_v2 as runtime


def _item(key, source, title, summary=""):
    return NewsItem(key, source, title, summary, f"https://example.com/{key}", "Sat, 05 Sep 2026 05:00:00 GMT")


def test_expanded_x_registry_contains_required_accounts():
    handles = {s["handle"] for s in builtin_x_news_sources()}
    required = {
        "@Reuters", "@AP", "@AFP", "@BBCWorld", "@CNN", "@FRANCE24", "@AJEnglish",
        "@AlArabiya_Eng", "@nytimes", "@nytimesworld", "@business", "@FT", "@SkyNews",
        "@NBCNews", "@CBSNews", "@ABC", "@FoxNews", "@dwnews", "@guardian", "@washingtonpost",
        "@WSJ", "@TheEconomist", "@netanyahu", "@Israel_katz", "@kann_news", "@N12News",
        "@newsisrael13", "@C14_news", "@IDF", "@Jerusalem_Post", "@IsraelHayomEng", "@CENTCOM",
        "@USTreasury", "@SecScottBessent", "@SecDef", "@SecRubio", "@VP", "@StateDept",
        "@statedeptspox", "@WhiteHouse", "@marklevinshow", "@JasonMBrodsky", "@mdubowitz",
        "@manniefabian", "@sfrantzman", "@jconricus", "@Doranimated", "@jmhansler", "@JoeTruzman",
        "@Tasnimnews_Fa", "@Tasnimnews_EN",
    }
    assert required <= handles


def test_no_iranian_commentators_are_in_expanded_x_registry():
    handles = {s["handle"].lower() for s in builtin_x_news_sources()}
    forbidden = {"@farzinnadimi", "@ksadjadpour", "@alirezanader", "@yarbatman"}
    assert not (handles & forbidden)


def test_x_monitor_query_covers_naval_nuclear_sanctions_and_frozen_funds():
    query = x_monitor_query().lower()
    for term in (
        "abraham lincoln", "uss boxer", "carrier strike group", "destroyer", "submarine",
        "fifth fleet", "navcent", "minelaying", "naval mine", "mine countermeasures", "hormuz",
        "al udeid", "al dhafra", "diego garcia", "fordow", "natanz", "isfahan", "centrifuge",
        "iaea", "grossi", "inspector", "enrichment", "uranium", "ofac", "sanctions",
        "frozen funds", "blocked funds", "ballistic missile", "cruise missile", "quds force",
    ):
        assert term in query


def test_x_post_text_removes_trailing_secondary_media_attribution():
    assert clean_x_post_text("Iran is examining whether tensions could escalate - i24NEWS") == "Iran is examining whether tensions could escalate"
    assert clean_x_post_text("Iran war is very unpopular - Wall Street Journal") == "Iran war is very unpopular"


def test_x_post_text_removes_parenthetical_secondary_media_citation():
    assert clean_x_post_text("Time is no longer on Iran's side (Wall Street Journal, 2018).") == "Time is no longer on Iran's side."
    assert clean_x_post_text("Pressure is rising (i24NEWS).") == "Pressure is rising."


class _FakeResponse:
    def __init__(self, url, text=""):
        self.url = url
        self.text = text
    def raise_for_status(self):
        return None


class _FakeSession:
    def __init__(self, response):
        self.response = response
    def get(self, *args, **kwargs):
        return self.response


def test_x_link_resolver_returns_direct_status_redirect():
    session = _FakeSession(_FakeResponse("https://x.com/Reuters/status/1961234567890123456"))
    assert resolve_x_post_url("https://news.google.com/rss/articles/abc", "Reuters", session=session) == "https://x.com/Reuters/status/1961234567890123456"


def test_x_link_resolver_extracts_status_url_from_google_wrapper_html():
    html = '<a href="https://x.com/Reuters/status/1961234567890123456?ref_src=twsrc%5Etfw">post</a>'
    session = _FakeSession(_FakeResponse("https://news.google.com/articles/abc", html))
    assert resolve_x_post_url("https://news.google.com/rss/articles/abc", "Reuters", session=session) == "https://x.com/Reuters/status/1961234567890123456"


def test_same_katz_claim_from_france24_and_ap_is_duplicate_despite_paraphrase():
    first = _item(
        "f24", "France 24 / X",
        "Israel Katz says Israel will strike Iran's nuclear sites again if Tehran rebuilds them",
        "The Israeli defence minister warned Tehran against restoring damaged nuclear facilities.",
    )
    second = _item(
        "ap", "Associated Press / X",
        "Israeli defense chief warns Tehran against rebuilding atomic facilities, threatens renewed strikes",
        "Katz said another attack would follow if Iran restores its nuclear program.",
    )
    assert is_duplicate_story(first, second)


def test_materially_new_katz_development_is_not_duplicate():
    first = _item("a", "France 24 / X", "Israel Katz threatens renewed strikes if Iran rebuilds nuclear sites")
    second = _item("b", "Reuters / X", "Israel Katz says strikes will begin Sunday at 04:00 if Iran rebuilds Fordow")
    assert not is_duplicate_story(first, second)


def test_news_wrapper_includes_country_flags_and_follow_arrow():
    item = _item(
        "flags", "Reuters / X",
        "US and Israel discuss new measures against Iran",
        "American and Israeli officials met about Iran.",
    )
    rendered = runtime._format_news_with_flags(
        item, "آمریکا و اسرائیل درباره اقدامات تازه علیه ایران گفت‌وگو کردند", ""
    )
    assert "🇮🇷" in rendered and "🇮🇱" in rendered and "🇺🇸" in rendered
    assert '👉🏻 📡 <a href="https://t.me/bikhabaar">بی‌خبر</a> ←' in "\n".join(runtime._brand_footer_with_arrow())


def test_oil_prices_are_added_to_market_output():
    snapshot = MarketSnapshot(2_210_600, 235_188_000)
    object.__setattr__(snapshot, "brent_usd", 112.35)
    object.__setattr__(snapshot, "wti_usd", 108.10)
    rendered = runtime._format_market_with_oil(snapshot)
    assert "نفت برنت: $112.35" in rendered
    assert "نفت WTI: $108.10" in rendered
    assert "منبع نفت: Yahoo Finance" in rendered


def test_oil_daily_change_reports_amount_and_percentage():
    up = "\n".join(runtime._oil_daily_lines("نفت برنت", 100.0, 110.0))
    down = "\n".join(runtime._oil_daily_lines("نفت WTI", 100.0, 95.0))
    assert "$10.00" in up and "10.00٪ افزایش" in up
    assert "$5.00" in down and "5.00٪ کاهش" in down


def test_oil_formatter_skips_missing_benchmarks_without_inventing_prices():
    assert format_oil_lines(OilSnapshot()) == []
