from src.formatters import format_news
from src.sources import NewsItem


def test_news_does_not_repeat_same_title_as_summary():
    item = NewsItem("k", "Reuters", "Iran talks - Reuters", "Iran talks Reuters", "https://example.com", "")
    text = format_news(item, "مذاکرات ایران", "مذاکرات ایران")
    assert text.count("مذاکرات ایران") == 1
    assert "لینک خبر" in text
