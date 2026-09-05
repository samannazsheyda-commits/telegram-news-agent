from src.newsroom_x import builtin_x_news_sources, fetch_builtin_x_news_items
from src.sources import NewsItem
import src.runtime_v2 as runtime


CORE_HANDLES = {
    "@Reuters", "@AP", "@AFP", "@BBCWorld", "@CNN", "@FRANCE24",
    "@AJEnglish", "@AlArabiya_Eng", "@TimesofIsrael", "@haaretzcom", "@axios",
}


def test_builtin_x_sources_cover_core_world_newsrooms():
    handles = {source["handle"] for source in builtin_x_news_sources()}
    assert CORE_HANDLES <= handles


def test_builtin_x_fetch_uses_x_source_labels():
    calls = []

    def searcher(source):
        calls.append(source)
        return [NewsItem("k", "Reuters / X", "Iran update", "Iran update detail", "https://x.com/Reuters/status/1", "Fri, 04 Sep 2026 10:00:00 GMT")]

    items = fetch_builtin_x_news_items(searcher=searcher)
    assert calls
    assert any(source["handle"] == "@Reuters" for source in calls)
    assert items
    assert all(item.source.endswith(" / X") for item in items)


def test_official_newsroom_x_item_gets_selection_priority_boost():
    x_item = NewsItem(
        "x", "Reuters / X", "Iran officials announce new security measure", "Iran security update.",
        "https://x.com/Reuters/status/1", "Fri, 04 Sep 2026 10:00:00 GMT",
    )
    web_item = NewsItem(
        "web", "Reuters", "Iran officials announce new security measure", "Iran security update.",
        "https://reuters.com/example", "Fri, 04 Sep 2026 10:00:00 GMT",
    )
    runtime._x_news_keys = {"x"}
    assert runtime._priority_event_priority(x_item) > runtime._priority_event_priority(web_item)
