from datetime import datetime, timezone

from src.sources import NewsItem


def _x(key: str, published: str, title: str = "Iran update") -> NewsItem:
    return NewsItem(key, "Reuters / X", title, "", f"https://x.com/Reuters/status/{key.split(':')[-1]}", published)


def test_easy_flow_accepts_x_without_editorial_rejection(monkeypatch):
    from src import runtime_v7 as v7

    item = _x("x:Reuters:2", "Thu, 03 Sep 2026 08:00:00 +0000")
    monkeypatch.setattr(v7.v6.v5.v4.v3.v2.base.agent, "_news_rejection_reason", lambda _item, _now: "not_today_tehran")

    v7.install_easy_news_flow()
    assert v7.v6.v5.v4.v3.v2.base.agent._news_rejection_reason(item, datetime(2026, 9, 5, tzinfo=timezone.utc)) is None


def test_easy_flow_selects_only_one_newest_story_per_cycle():
    from src import runtime_v7 as v7

    items = [
        _x("x:Reuters:1", "Sat, 05 Sep 2026 08:00:00 +0000"),
        _x("x:Reuters:2", "Sat, 05 Sep 2026 08:01:00 +0000"),
        _x("x:Reuters:3", "Sat, 05 Sep 2026 08:02:00 +0000"),
    ]
    selected, skipped = v7._select_one_story(items, [])
    assert [item.key for item in selected] == ["x:Reuters:3"]
    assert skipped == []


def test_distinct_x_posts_are_not_semantically_deduped():
    from src import runtime_v7 as v7

    older = _x("x:Reuters:1", "Sat, 05 Sep 2026 08:00:00 +0000", "Iran tanker hit near Kharg")
    newer = _x("x:Reuters:2", "Sat, 05 Sep 2026 08:01:00 +0000", "Iran tanker hit near Kharg")
    selected, skipped = v7._select_one_story([newer], [older])
    assert [item.key for item in selected] == ["x:Reuters:2"]
    assert skipped == []
