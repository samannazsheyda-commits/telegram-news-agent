from src.formatters import format_news, format_truth
from src.sources import NewsItem, TruthPost


def test_news_does_not_repeat_same_title_as_summary():
    item = NewsItem("k", "Reuters", "Iran talks - Reuters", "Iran talks Reuters", "https://example.com", "")
    text = format_news(item, "مذاکرات ایران", "مذاکرات ایران")
    assert text.count("مذاکرات ایران") == 1
    assert "لینک خبر" in text


def test_news_footer_has_clickable_bikhabar_and_tagline_after_source():
    item = NewsItem("k", "Reuters", "Iran", "summary", "https://example.com", "")
    text = format_news(item, "خبر ایران", "خلاصه")
    assert '<a href="https://t.me/bikhabaar">بی‌خبر</a>' in text
    assert "رسانه خبر ایران" in text
    assert text.index("لینک خبر") < text.index("بی‌خبر")


def test_truth_footer_has_clickable_bikhabar_and_tagline():
    post = TruthPost("1", "", "Iran", "https://truthsocial.com/post/1")
    text = format_truth(post, "متن فارسی")
    assert '<a href="https://t.me/bikhabaar">بی‌خبر</a>' in text
    assert "رسانه خبر ایران" in text
