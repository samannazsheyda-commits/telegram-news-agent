from datetime import datetime, timezone

from src.sources import NewsItem


def _x(key: str, published: str, title: str = "Iran update") -> NewsItem:
    return NewsItem(key, "Reuters / X", title, "", f"https://x.com/Reuters/status/{key.split(':')[-1]}", published)


def test_easy_flow_accepts_x_without_editorial_rejection():
    from src import runtime_v7 as v7

    item = _x("x:Reuters:2", "Thu, 03 Sep 2026 08:00:00 +0000")
    assert v7._easy_rejection_reason(item, datetime(2026, 9, 5, tzinfo=timezone.utc)) is None


def test_easy_flow_rejects_x_post_without_iran_anchor():
    from src import runtime_v7 as v7

    item = NewsItem(
        "x:kann:1",
        "KAN 11 / X",
        "שגריר ארה\"ב בישראל במהלך ביקורו בכפר הפלסטיני ליד רמאללה",
        "",
        "https://x.com/kann_news/status/1",
        "Sat, 05 Sep 2026 08:00:00 +0000",
    )
    assert v7._easy_rejection_reason(item, datetime(2026, 9, 5, tzinfo=timezone.utc)) == "not_iran_related"


def test_translation_failure_does_not_fall_back_to_hebrew(monkeypatch):
    from src import runtime_v7 as v7

    monkeypatch.setattr(v7, "_original_translate", lambda value, session=None: "")
    hebrew = "שגריר ארה\"ב בישראל"
    assert v7._translate_or_original(hebrew) == ""


def test_install_easy_flow_wires_policy_without_leaking_after_test(monkeypatch):
    from src import runtime_v7 as v7

    original_reason = v7.v2.base.agent._news_rejection_reason
    original_selector = v7.v2.base.agent._select_top_stories
    original_translate = v7.v2.translate_news_to_fa
    original_strict = v7.v2._strict_rejection_reason
    original_flag = v7._easy_news_flow_installed

    try:
        v7._easy_news_flow_installed = False
        v7.install_easy_news_flow()
        assert v7.v2.base.agent._news_rejection_reason is v7._easy_rejection_reason
        assert v7.v2.base.agent._select_top_stories is v7._select_one_story
    finally:
        v7.v2.base.agent._news_rejection_reason = original_reason
        v7.v2.base.agent._select_top_stories = original_selector
        v7.v2.translate_news_to_fa = original_translate
        v7.v2._strict_rejection_reason = original_strict
        v7._easy_news_flow_installed = original_flag


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
