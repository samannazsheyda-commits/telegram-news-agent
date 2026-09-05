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


def test_x_without_direct_status_link_is_rejected():
    from src import runtime_v7 as v7

    item = NewsItem(
        "x:Reuters:4",
        "Reuters / X",
        "Iran says talks will continue",
        "",
        "",
        "Sat, 05 Sep 2026 08:00:00 +0000",
    )
    assert v7._easy_rejection_reason(item, datetime(2026, 9, 5, tzinfo=timezone.utc)) == "missing_direct_source_link"


def test_x_with_non_status_link_is_rejected():
    from src import runtime_v7 as v7

    item = NewsItem(
        "x:Reuters:5",
        "Reuters / X",
        "Iran says talks will continue",
        "",
        "https://x.com/Reuters",
        "Sat, 05 Sep 2026 08:00:00 +0000",
    )
    assert v7._easy_rejection_reason(item, datetime(2026, 9, 5, tzinfo=timezone.utc)) == "missing_direct_source_link"


def test_translation_failure_does_not_fall_back_to_hebrew(monkeypatch):
    from src import runtime_v7 as v7

    monkeypatch.setattr(v7, "_original_translate", lambda value, session=None: "")
    hebrew = "שגריר ארה\"ב בישראל"
    assert v7._translate_or_original(hebrew) == ""


def test_translation_failure_does_not_fall_back_to_english(monkeypatch):
    from src import runtime_v7 as v7

    monkeypatch.setattr(v7, "_original_translate", lambda value, session=None: "")
    assert v7._translate_or_original("Iran says talks will continue") == ""


def test_bad_translation_that_is_still_english_is_rejected(monkeypatch):
    from src import runtime_v7 as v7

    monkeypatch.setattr(v7, "_original_translate", lambda value, session=None: "Iran says talks will continue")
    assert v7._translate_or_original("Iran says talks will continue") == ""


def test_mixed_english_with_one_persian_word_is_not_treated_as_persian(monkeypatch):
    from src import runtime_v7 as v7

    monkeypatch.setattr(v7, "_original_translate", lambda value, session=None: "")
    assert v7._translate_or_original("Breaking ایران missile update from Reuters") == ""


def test_persian_source_text_can_pass_without_translation(monkeypatch):
    from src import runtime_v7 as v7

    monkeypatch.setattr(v7, "_original_translate", lambda value, session=None: "")
    assert v7._translate_or_original("ایران اعلام کرد مذاکرات ادامه دارد") == "ایران اعلام کرد مذاکرات ادامه دارد"


def test_formatter_refuses_news_without_source_link():
    from src import runtime_v7 as v7

    item = NewsItem(
        "x:Reuters:6",
        "Reuters / X",
        "Iran update",
        "",
        "",
        "Sat, 05 Sep 2026 08:00:00 +0000",
    )
    assert v7._format_news_with_footer_icons(item, "ایران خبر تازه‌ای منتشر کرد", "") == ""


def test_formatter_refuses_non_persian_title_even_if_link_exists():
    from src import runtime_v7 as v7

    item = _x("x:Reuters:7", "Sat, 05 Sep 2026 08:00:00 +0000")
    assert v7._format_news_with_footer_icons(item, "Iran update from Reuters", "") == ""


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
