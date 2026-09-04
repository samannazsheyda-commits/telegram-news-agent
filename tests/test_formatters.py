from datetime import datetime, timezone

from src.formatters import format_market, format_news, format_truth
from src.sources import MarketSnapshot, NewsItem, TruthPost


def test_news_does_not_repeat_same_title_as_summary():
    item = NewsItem("k", "Reuters", "Iran talks - Reuters", "Iran talks Reuters", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    text = format_news(item, "مذاکرات ایران", "مذاکرات ایران", marker_override="⚪️")
    assert text.count("مذاکرات ایران") == 1
    assert "لینک منبع خبر" in text


def test_news_footer_has_clickable_bikhabar_and_tagline_after_link():
    item = NewsItem("k", "Reuters", "Iran", "summary", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    text = format_news(item, "خبر ایران", "خلاصه", marker_override="⚪️")
    assert '<a href="https://t.me/bikhabaar">بی‌خبر</a>' in text
    assert "مانیتور تحولات ایران" in text
    assert text.index("لینک منبع خبر") < text.index("بی‌خبر")


def test_truth_footer_has_clickable_bikhabar_and_tagline():
    post = TruthPost("1", "", "Iran", "https://truthsocial.com/post/1")
    text = format_truth(post, "متن فارسی")
    assert '<a href="https://t.me/bikhabaar">بی‌خبر</a>' in text
    assert "مانیتور تحولات ایران" in text


def test_news_starts_with_persian_source_then_headline_and_does_not_repeat_source_below():
    item = NewsItem("k", "Al Jazeera", "Iran talks", "details", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    text = format_news(item, "کره جنوبی مشارکت در تنگه هرمز را بررسی می‌کند", "", marker_override="⚪️")
    first_line = text.splitlines()[0]
    assert first_line.startswith("⚪️ <b>الجزیره: ")
    assert "کره جنوبی مشارکت در تنگه هرمز را بررسی می‌کند." in first_line
    assert "منبع: Al Jazeera" not in text
    assert "📌 <a href=\"https://example.com\">لینک منبع خبر</a>" in text


def test_news_time_has_only_date_and_time_without_tehran_phrase():
    item = NewsItem("k", "Reuters", "Iran talks", "details", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    text = format_news(item, "مذاکرات ایران", "جزئیات", marker_override="⚪️")
    assert "⏰" in text
    assert "۱۳:۳۰" in text
    assert "۱۴۰۵" in text
    assert "به وقت ایران" not in text


def test_market_contains_full_requested_watchlist_and_timestamp():
    snap = MarketSnapshot(
        usd_rial=2_210_600,
        gold18_rial=235_188_000,
        eur_rial=2_577_900,
        gbp_rial=2_970_000,
        aed_rial=602_000,
        try_rial=46_700,
        emami_rial=2_340_100_000,
        half_rial=1_200_000_000,
        quarter_rial=660_000_000,
        gram_coin_rial=350_000_000,
        bitcoin_usd=77_850.12,
        tether_rial=2_213_500,
    )
    text = format_market(snap, datetime(2026, 9, 4, 16, 35, tzinfo=timezone.utc))
    for label in ("دلار آزاد", "یورو", "پوند", "درهم", "لیر", "طلای ۱۸", "سکه امامی", "نیم‌سکه", "ربع‌سکه", "سکه گرمی", "بیت‌کوین", "تتر"):
        assert label in text
    assert "⏰" in text
    assert "۱۳ شهریور ۱۴۰۵" in text
    assert "۲۰:۰۵" in text
    assert "به وقت ایران" not in text
