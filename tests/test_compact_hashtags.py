from datetime import datetime, timezone

from src.formatters import format_market, format_news, format_truth
from src.sources import MarketSnapshot, NewsItem, TruthPost


def _last_nonempty_line(text: str) -> str:
    return [line for line in text.splitlines() if line.strip()][-1]


def test_news_adds_at_most_two_short_topic_hashtags_at_very_end():
    item = NewsItem(
        "k", "Reuters",
        "Explosion hits tanker near Strait of Hormuz",
        "A tanker was damaged after an explosion near the strait.",
        "https://example.com/story",
        "Fri, 04 Sep 2026 10:00:00 GMT",
    )
    text = format_news(item, "انفجار در نفتکش نزدیک تنگه هرمز", "یک نفتکش آسیب دید", marker_override="🛑")
    assert _last_nonempty_line(text) == "#انفجار #هرمز"
    assert len(_last_nonempty_line(text).split()) <= 2
    assert text.index("مانیتور تحولات ایران") < text.index("#انفجار")


def test_sanctions_news_uses_single_relevant_hashtag():
    item = NewsItem(
        "k", "Reuters", "US imposes new Iran sanctions", "",
        "https://example.com/sanctions", "Fri, 04 Sep 2026 10:00:00 GMT",
    )
    text = format_news(item, "آمریکا تحریم‌های تازه‌ای علیه ایران اعمال کرد", "", marker_override="🟥")
    assert _last_nonempty_line(text) == "#تحریم"


def test_truth_post_has_trump_hashtag_at_end():
    post = TruthPost("1", "", "Iran", "https://truthsocial.com/post/1")
    text = format_truth(post, "ترامپ درباره ایران نوشت")
    assert _last_nonempty_line(text).startswith("#ترامپ")
    assert len(_last_nonempty_line(text).split()) <= 2


def test_market_post_ends_with_dollar_and_gold_hashtags():
    snap = MarketSnapshot(
        usd_rial=2_210_600, gold18_rial=235_188_000, eur_rial=2_577_900, gbp_rial=2_970_000,
        aed_rial=602_000, try_rial=46_700, emami_rial=2_340_100_000, half_rial=1_200_000_000,
        quarter_rial=660_000_000, gram_coin_rial=350_000_000, bitcoin_usd=77_850.12, tether_rial=2_213_500,
    )
    text = format_market(snap, datetime(2026, 9, 4, 16, 35, tzinfo=timezone.utc))
    assert _last_nonempty_line(text) == "#دلار #طلا"
