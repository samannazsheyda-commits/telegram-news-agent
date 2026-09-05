from src.newsroom_x import clean_x_post_text
from src.runtime_v2 import _format_news_with_flags
from src.sources import NewsItem


def test_x_post_text_drops_leading_alert_emoji_and_urls():
    raw = (
        "🔴 BREAKING: Iranian media report blasts near Kharg Island. "
        "https://example.com/story"
    )
    assert clean_x_post_text(raw) == "BREAKING: Iranian media report blasts near Kharg Island."


def test_x_post_text_drops_trailing_live_updates_promo():
    raw = "BREAKING: An Iranian tanker was hit. 🔴 LIVE updates: https://aje.news/39nt0j"
    assert clean_x_post_text(raw) == "BREAKING: An Iranian tanker was hit."


def test_country_flags_are_below_source_link_and_above_brand_footer():
    item = NewsItem(
        "x:test:1",
        "Al Arabiya English / X",
        "Iran blast near Kharg Island",
        "",
        "https://x.com/test/status/1",
        "Sat, 05 Sep 2026 06:59:00 +0000",
    )

    text = _format_news_with_flags(
        item,
        "فوری: رسانه‌های ایران از شنیده شدن صدای انفجار در نزدیکی جزیره خارک خبر می‌دهند",
        "",
        marker_override="🛑",
    )

    assert text.count("🛑") == 1
    assert text.index("📌") < text.index("🇮🇷") < text.index("📡")
