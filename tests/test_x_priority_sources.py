from datetime import datetime, timezone

from src.formatters import format_news
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


def test_newsroom_fetch_does_not_mix_back_in_website_news(monkeypatch):
    x_item = NewsItem(
        "x", "Reuters / X", "Iran update from X", "", "https://x.com/Reuters/status/1",
        "Fri, 04 Sep 2026 10:00:00 GMT",
    )
    monkeypatch.setattr(runtime, "fetch_builtin_x_news_items", lambda: [x_item])

    def should_not_run():
        raise AssertionError("generic newsroom website fetch must stay disabled")

    monkeypatch.setattr(runtime, "_original_generic_fetch", should_not_run)
    assert runtime._x_first_fetch_news_items() == [x_item]


def test_official_x_source_name_is_rendered_in_persian():
    item = NewsItem(
        "ajx", "Al Jazeera English / X", "Iran update", "", "https://x.com/AJEnglish/status/1",
        "Fri, 04 Sep 2026 23:45:00 GMT",
    )
    rendered = format_news(item, "تازه‌ترین خبر درباره ایران", "")
    assert "الجزیره انگلیسی / ایکس" in rendered
    assert "Al Jazeera English / X" not in rendered


def test_fresh_iran_related_newsroom_x_post_is_allowed_even_without_breaking_terms():
    item = NewsItem(
        "ajx2", "Al Jazeera English / X",
        "Iran foreign ministry spokesman criticises a Jerusalem Post editorial",
        "The Iranian spokesman posted the criticism on X.",
        "https://x.com/AJEnglish/status/2", "Sat, 05 Sep 2026 02:00:00 GMT",
    )
    now = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)
    assert runtime._strict_rejection_reason(item, now) is None


def test_x_posts_do_not_fetch_article_body_for_extra_context():
    item = NewsItem(
        "rx", "Reuters / X", "Iran update from Reuters on X", "A short X post.",
        "https://x.com/Reuters/status/3", "Sat, 05 Sep 2026 02:00:00 GMT",
    )
    assert runtime.fetch_news_detail_x_only(item) == ""
