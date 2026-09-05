from src.sources import NewsItem


def _x(i: int) -> NewsItem:
    return NewsItem(
        f"x:Reuters:{i}",
        "Reuters / X",
        f"Iran update {i}",
        "",
        f"https://x.com/Reuters/status/{i}",
        f"Sat, 05 Sep 2026 08:{i:02d}:00 +0000",
    )


def test_selector_does_not_hold_ready_news_for_a_later_cycle(monkeypatch):
    from src import runtime_v7 as v7

    monkeypatch.setattr(v7, "_original_translate", lambda value, session=None: "خبر فارسی معتبر درباره ایران")
    v7._translation_cache.clear()
    items = [_x(i) for i in range(1, 8)]

    selected, skipped = v7._select_one_story(items, [])

    assert [item.key for item in selected] == [
        "x:Reuters:7",
        "x:Reuters:6",
        "x:Reuters:5",
        "x:Reuters:4",
        "x:Reuters:3",
        "x:Reuters:2",
        "x:Reuters:1",
    ]
    assert skipped == []
