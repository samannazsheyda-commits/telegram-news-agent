from src.editorial_rules import is_duplicate_story
from src.formatters import format_news
from src.newsroom_x import builtin_x_news_sources, x_monitor_query
from src.sources import NewsItem


def _item(key, source, title, summary=""):
    return NewsItem(key, source, title, summary, f"https://example.com/{key}", "Sat, 05 Sep 2026 05:00:00 GMT")


def test_expanded_x_registry_contains_required_accounts():
    handles = {s["handle"] for s in builtin_x_news_sources()}
    required = {
        "@Reuters", "@AP", "@AFP", "@BBCWorld", "@CNN", "@FRANCE24", "@AJEnglish",
        "@AlArabiya_Eng", "@nytimes", "@nytimesworld", "@business", "@FT", "@SkyNews",
        "@NBCNews", "@CBSNews", "@ABC", "@FoxNews", "@dwnews", "@guardian", "@washingtonpost",
        "@WSJ", "@netanyahu", "@Israel_katz", "@kann_news", "@N12News", "@newsisrael13",
        "@C14_news", "@IDF", "@Jerusalem_Post", "@IsraelHayomEng", "@CENTCOM", "@USTreasury",
        "@SecScottBessent", "@SecDef", "@StateDept", "@statedeptspox", "@WhiteHouse",
        "@marklevinshow", "@JasonMBrodsky", "@Tasnimnews_Fa", "@Tasnimnews_EN",
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


def test_news_includes_country_flags_and_follow_arrow():
    item = _item(
        "flags", "Reuters / X",
        "US and Israel discuss new measures against Iran",
        "American and Israeli officials met about Iran.",
    )
    rendered = format_news(item, "آمریکا و اسرائیل درباره اقدامات تازه علیه ایران گفت‌وگو کردند", "")
    assert "🇮🇷" in rendered and "🇮🇱" in rendered and "🇺🇸" in rendered
    assert '👉🏻 📡 <a href="https://t.me/bikhabaar">بی‌خبر</a> ←' in rendered
