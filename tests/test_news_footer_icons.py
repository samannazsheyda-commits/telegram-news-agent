from src.sources import NewsItem


def test_flags_and_topic_icons_are_last_line_after_brand_footer():
    from src import runtime_v7 as v7

    item = NewsItem(
        "x:Reuters:123",
        "Reuters / X",
        "Iran missile strike hits tanker near Kharg Island",
        "smoke reported after the attack",
        "https://x.com/Reuters/status/123",
        "Sat, 05 Sep 2026 10:00:00 +0000",
    )
    text = v7._format_news_with_footer_icons(item, "حمله موشکی ایران به نفتکش نزدیک خارک", "پس از حمله دود مشاهده شد")
    lines = [line for line in text.splitlines() if line.strip()]

    assert "مانیتور تحولات ایران" in lines[-2]
    assert "🇮🇷" in lines[-1]
    assert "🚀" in lines[-1]
    assert "🚢" in lines[-1]
    assert "💨" in lines[-1]
