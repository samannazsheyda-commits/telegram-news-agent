from src.formatters import format_market, format_news, format_truth
from src.sources import MarketSnapshot, NewsItem, TruthPost


def test_news_does_not_repeat_same_title_as_summary():
    item = NewsItem("k", "Reuters", "Iran talks - Reuters", "Iran talks Reuters", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    text = format_news(item, "مذاکرات ایران", "مذاکرات ایران")
    assert text.count("مذاکرات ایران") == 1
    assert "لینک خبر" in text


def test_news_footer_has_clickable_bikhabar_and_tagline_after_source():
    item = NewsItem("k", "Reuters", "Iran", "summary", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    text = format_news(item, "خبر ایران", "خلاصه")
    assert '<a href="https://t.me/bikhabaar">بی‌خبر</a>' in text
    assert "مانیتور تحولات ایران" in text
    assert text.index("لینک خبر") < text.index("بی‌خبر")


def test_truth_footer_has_clickable_bikhabar_and_tagline():
    post = TruthPost("1", "", "Iran", "https://truthsocial.com/post/1")
    text = format_truth(post, "متن فارسی")
    assert '<a href="https://t.me/bikhabaar">بی‌خبر</a>' in text
    assert "مانیتور تحولات ایران" in text


def test_news_starts_with_topic_emoji_bold_title_and_terminal_punctuation():
    item = NewsItem("k", "Axios", "Iran missile attack", "missile strike", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    text = format_news(item, "حمله موشکی به ایران", "جزئیات حمله")
    first_line = text.splitlines()[0]
    assert first_line == "🚀 <b>حمله موشکی به ایران.</b>"
    assert "Axios | ایران" not in text
    assert "🔗 منبع: Axios" in text


def test_news_shows_source_publication_time_in_tehran_time():
    item = NewsItem("k", "Reuters", "Iran talks", "details", "https://example.com", "Fri, 04 Sep 2026 10:00:00 GMT")
    text = format_news(item, "مذاکرات ایران", "جزئیات")
    assert "🕒" in text
    assert "۱۳:۳۰" in text
    assert "۱۴۰۵" in text


def test_market_contains_full_requested_watchlist():
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
    text = format_market(snap)
    for label in ("دلار آزاد", "یورو", "پوند", "درهم", "لیر", "طلای ۱۸", "سکه امامی", "نیم‌سکه", "ربع‌سکه", "سکه گرمی", "بیت‌کوین", "تتر"):
        assert label in text
