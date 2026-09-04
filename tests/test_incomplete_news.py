from src.formatters import format_news
from src.sources import NewsItem


def _item():
    return NewsItem(
        "fox-activist",
        "Fox News",
        "Human rights activist warns Iran prefers conflict with US to peace",
        "Comprehensive up-to-date news coverage, aggregated from sources all over the world by Google News.",
        "https://example.com/fox",
        "Fri, 04 Sep 2026 22:00:00 GMT",
    )


def test_google_news_boilerplate_is_never_published_as_detail():
    text = format_news(
        _item(),
        "فعال حقوق بشر هشدار می‌دهد ایران درگیری با آمریکا را به صلح ترجیح می‌دهد",
        "پوشش جامع و به‌روز اخبار، جمع‌آوری‌شده از منابع مختلف در سراسر جهان توسط گوگل نیوز.",
        marker_override="🟥",
    )
    assert "پوشش جامع" not in text
    assert "گوگل نیوز" not in text


def test_unnamed_person_headline_without_real_detail_is_rejected():
    text = format_news(
        _item(),
        "فعال حقوق بشر هشدار می‌دهد ایران درگیری با آمریکا را به صلح ترجیح می‌دهد",
        "پوشش جامع و به‌روز اخبار، جمع‌آوری‌شده از منابع مختلف در سراسر جهان توسط گوگل نیوز.",
        marker_override="🟥",
    )
    assert text == ""


def test_unnamed_person_headline_is_allowed_when_real_detail_names_person():
    text = format_news(
        _item(),
        "فعال حقوق بشر هشدار می‌دهد ایران درگیری با آمریکا را به صلح ترجیح می‌دهد",
        "مسیح علی‌نژاد، فعال حقوق بشر ایرانی، گفت حکومت برای مهار اعتراضات داخلی از تشدید تنش خارجی استفاده می‌کند.",
        marker_override="🟥",
    )
    assert "مسیح علی‌نژاد" in text
    assert "فاکس نیوز" in text
