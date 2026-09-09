from datetime import datetime, timezone

from src.newsroom_raw_intake import news_item_to_raw, build_raw_fetchers
from src.sources import NewsItem


def test_news_item_to_raw_preserves_source_identity_and_text():
    item = NewsItem(
        key="source-key-1",
        source="Reuters",
        title="Iran announces a new shipping restriction",
        summary="A distinct operational update.",
        link="https://example.com/story",
        published="Mon, 07 Sep 2026 18:00:00 +0000",
    )
    raw = news_item_to_raw(item, fetched_at="2026-09-07T18:01:00+00:00")
    assert raw.source_item_id == "source-key-1"
    assert raw.source == "Reuters"
    assert raw.source_url == "https://example.com/story"
    assert raw.title == item.title
    assert raw.summary == item.summary


def test_build_raw_fetchers_keeps_sources_isolated_and_adds_direct_x_and_truth_lanes():
    calls = []

    def direct_x():
        calls.append("direct_x")
        return [NewsItem("x", "CENTCOM / X", "X", "", "https://x.com/CENTCOM/status/1", "Mon, 07 Sep 2026 18:00:00 +0000")]

    def base():
        calls.append("base")
        return [NewsItem("a", "Reuters", "A", "", "https://a", "Mon, 07 Sep 2026 18:00:00 +0000")]

    def custom():
        calls.append("custom")
        return [NewsItem("b", "Custom", "B", "", "https://b", "Mon, 07 Sep 2026 18:00:00 +0000")]

    def priority():
        calls.append("priority")
        return [NewsItem("c", "Priority", "C", "", "https://c", "Mon, 07 Sep 2026 18:00:00 +0000")]

    def truth():
        calls.append("truth")
        return []

    fetchers = build_raw_fetchers(
        direct_x_fetch=direct_x,
        base_fetch=base,
        custom_fetch=custom,
        priority_fetch=priority,
        truth_fetch=truth,
    )
    assert len(fetchers) == 5
    batches = [fn() for fn in fetchers]
    assert calls == ["direct_x", "custom", "truth", "priority", "base"]
    assert batches[0][0].source_item_id == "x"
    assert batches[1][0].source_item_id == "b"
    assert batches[3][0].source_item_id == "c"
    assert batches[4][0].source_item_id == "a"
