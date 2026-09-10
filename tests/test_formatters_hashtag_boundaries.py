from src.formatters import format_news
from src.sources import NewsItem


def test_gold_hashtag_does_not_match_inside_persian_word_information():
    item = NewsItem(
        "reuters-houthis",
        "Reuters / X",
        "Iran-backed Houthis seized a key Yemeni port city, giving them more control over Red Sea shipping. Learn more in the Reuters World News podcast afternoon update.",
        "",
        "https://x.com/Reuters/status/2098159199825895822",
        "Thu, 10 Sep 2026 21:18:00 GMT",
    )
    text = format_news(
        item,
        "حوثی‌های مورد حمایت ایران یک شهر بندری مهم یمن را تصرف کرده‌اند و کنترل بیشتری بر کشتی‌رانی دریای سرخ پیدا کرده‌اند. در به‌روزرسانی بعدازظهر پادکست اخبار جهانی رویترز اطلاعات بیشتری کسب کنید",
        "",
        marker_override="🛑",
    )
    assert "#طلا" not in text
