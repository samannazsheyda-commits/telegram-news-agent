from datetime import datetime, timezone

from src.formatters import format_market, format_market_daily_summary, format_news, format_truth
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


def test_truth_has_explicit_source_and_footer():
    post = TruthPost("1", "", "Iran", "https://truthsocial.com/post/1")
    text = format_truth(post, "متن فارسی")
    assert "منبع: Truth Social" in text
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


def test_al_arabiya_is_persian_and_source_suffix_is_removed_from_headline():
    item = NewsItem("arabiya", "Al Arabiya", "US issues new Iran-related sanctions and general license - Al Arabiya English", "", "https://example.com/arabiya", "Fri, 04 Sep 2026 14:18:00 GMT")
    text = format_news(item, "آمریکا تحریم‌های جدید مرتبط با ایران و مجوز عمومی صادر کرد - العربیه انگلیسی", "", marker_override="🟥")
    first_line = text.splitlines()[0]
    assert first_line == "🟥 <b>العربیه: آمریکا تحریم‌های جدید مرتبط با ایران و مجوز عمومی صادر کرد.</b>"
    assert "Al Arabiya" not in text
    assert "العربیه انگلیسی" not in text


def test_new_major_sources_are_shown_in_persian():
    expected = {
        "KAN 11": "کانال ۱۱ اسرائیل", "N12": "کانال ۱۲ اسرائیل", "Channel 13": "کانال ۱۳ اسرائیل",
        "Fox News": "فاکس نیوز", "NBC News": "ان‌بی‌سی نیوز", "CBS News": "سی‌بی‌اس نیوز",
        "ABC News": "ای‌بی‌سی نیوز", "Sky News": "اسکای نیوز", "Bloomberg": "بلومبرگ", "CNBC": "سی‌ان‌بی‌سی",
        "Sepah News / X": "سپاه نیوز",
    }
    for source, fa in expected.items():
        item = NewsItem("k", source, "Iran", "", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
        text = format_news(item, "خبر مهم ایران", "", marker_override="⚪️")
        assert text.splitlines()[0].startswith(f"⚪️ <b>{fa}: ")


def test_news_keeps_two_useful_detail_sentences_not_only_one():
    item = NewsItem("k", "Reuters", "Iran sanctions", "details", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    summary = "این مهم‌ترین نکته خبر است. این توضیح دوم برای روشن شدن خبر لازم است. این جمله سوم دیگر منتشر نمی‌شود."
    text = format_news(item, "تحریم‌های تازه علیه ایران اعمال شد", summary, marker_override="🟥")
    assert "این مهم‌ترین نکته خبر است." in text
    assert "این توضیح دوم برای روشن شدن خبر لازم است." in text
    assert "این جمله سوم" not in text


def test_formatter_never_chops_normal_comma_clause_into_incomplete_fragment():
    item = NewsItem("toi", "Times of Israel", "Jordan, which has repeatedly been attacked by Iran, activated defenses", "", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    title = "اردن که بارها مورد حمله ایران قرار گرفته، سامانه‌های دفاعی خود را فعال کرد"
    text = format_news(item, title, "", marker_override="🛑")
    assert "سامانه‌های دفاعی خود را فعال کرد" in text.splitlines()[0]


def test_news_time_has_only_date_and_time_without_tehran_phrase():
    item = NewsItem("k", "Reuters", "Iran talks", "details", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    text = format_news(item, "مذاکرات ایران", "جزئیات", marker_override="⚪️")
    assert "⏰" in text
    assert "۱۳:۳۰" in text
    assert "۱۴۰۵" in text
    assert "به وقت ایران" not in text


def test_market_contains_full_requested_watchlist_timestamp_source_and_footer():
    snap = MarketSnapshot(
        usd_rial=2_210_600, gold18_rial=235_188_000, eur_rial=2_577_900, gbp_rial=2_970_000,
        aed_rial=602_000, try_rial=46_700, emami_rial=2_340_100_000, half_rial=1_200_000_000,
        quarter_rial=660_000_000, gram_coin_rial=350_000_000, bitcoin_usd=77_850.12, tether_rial=2_213_500,
    )
    text = format_market(snap, datetime(2026, 9, 4, 16, 35, tzinfo=timezone.utc))
    for label in ("دلار آزاد", "یورو", "پوند", "درهم", "لیر", "طلای ۱۸", "سکه امامی", "نیم‌سکه", "ربع‌سکه", "سکه گرمی", "بیت‌کوین", "تتر"):
        assert label in text
    assert "⏰" in text and "۱۳ شهریور ۱۴۰۵" in text and "۲۰:۰۵" in text
    assert "به وقت ایران" not in text
    assert "منبع: TGJU" in text
    assert "بی‌خبر" in text


def test_daily_market_summary_reports_amount_and_percentage_with_source():
    text = format_market_daily_summary(
        200_000, 210_000, 20_000_000, 19_000_000,
        datetime(2026, 9, 4, 20, 30, tzinfo=timezone.utc),
    )
    assert "۱۰,۰۰۰ تومان" in text
    assert "5.00٪ افزایش" in text
    assert "۱,۰۰۰,۰۰۰ تومان / گرم" in text
    assert "5.00٪ کاهش" in text
    assert "منبع: TGJU" in text
