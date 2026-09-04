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
    assert "مانیتور تحولات ایران" in text
    assert text.index("لینک خبر") < text.index("بی‌خبر")


def test_truth_footer_has_clickable_bikhabar_and_tagline():
    post = TruthPost("1", "", "Iran", "https://truthsocial.com/post/1")
    text = format_truth(post, "متن فارسی")
    assert '<a href="https://t.me/bikhabaar">بی‌خبر</a>' in text
    assert "مانیتور تحولات ایران" in text


def test_news_uses_topic_emoji_and_removes_source_header():
    item = NewsItem("k", "Axios", "Iran missile attack", "missile strike", "https://example.com", "")
    text = format_news(item, "حمله موشکی به ایران", "جزئیات حمله")
    first_line = text.splitlines()[0]
    assert first_line == "🚀"
    assert "Axios | ایران" not in text
    assert "منبع: Axios" in text


def test_news_topic_emoji_for_hormuz_and_talks():
    hormuz = NewsItem("h", "Reuters", "Strait of Hormuz tanker", "shipping", "https://example.com/h", "")
    talks = NewsItem("t", "Reuters", "Iran ceasefire talks", "negotiations", "https://example.com/t", "")
    assert format_news(hormuz, "نفتکش در تنگه هرمز", "جزئیات").splitlines()[0] == "⚓"
    assert format_news(talks, "مذاکرات آتش‌بس ایران", "جزئیات").splitlines()[0] == "🤝"
