from __future__ import annotations

import re

from src.formatters import format_news
from src.sources import NewsItem


def _item(*, title="", summary="", source="Reuters", published="Wed, 09 Sep 2026 15:30:00 +0000", link="https://example.com/news"):
    return NewsItem(
        key="guideline-1",
        source=source,
        title=title,
        summary=summary,
        link=link,
        published=published,
    )


def test_news_uses_source_time_in_tehran_with_weekday_shamsi_and_persian_digits():
    message = format_news(_item(title="Iran update", summary=""), "خبر تازه از ایران", "")
    assert "⏰ چهارشنبه ۱۸ شهریور ۱۴۰۵ — ۱۹:۰۰" in message
    assert "2026" not in message
    assert "15:30" not in message
    assert '📌 <a href="https://example.com/news">لینک منبع خبر</a>' in message
    assert '📡 <a href="https://t.me/bikhabaar">بی‌خبر</a> ←' in message
    assert "مانیتور تحولات ایران" in message


def test_news_omits_timestamp_when_source_time_is_missing():
    message = format_news(_item(title="Iran update", published=""), "خبر تازه از ایران", "")
    assert "⏰" not in message


def test_missile_and_explosion_have_fast_breaking_markers_and_compact_hashtags():
    missile = format_news(
        _item(title="Iran launches ballistic missile toward Israel", summary="missile launch"),
        "ایران یک موشک بالستیک به سمت اسرائیل شلیک کرد",
        "شلیک موشک تأیید شده است",
    )
    assert missile.startswith("🚨🚀")
    assert "#موشک" in missile
    assert len(re.findall(r"(?<!\w)#[\w\u0600-\u06ff‌]+", missile)) <= 2

    explosion = format_news(
        _item(title="Explosion heard in Tehran", summary="blast reported"),
        "صدای انفجار در تهران شنیده شد",
        "جزئیات بیشتری هنوز منتشر نشده است",
    )
    assert explosion.startswith("🟥💥")
    assert "#انفجار" in explosion
    assert len(re.findall(r"(?<!\w)#[\w\u0600-\u06ff‌]+", explosion)) <= 2


def test_final_news_strips_source_handles_english_alert_tokens_flags_and_html_newline_entity():
    message = format_news(
        _item(title="BREAKING alert", source="Middle East Spectator / Telegram"),
        "BREAKING: هشدار فوری 🇸🇦 @Middle_East_Spectator",
        "ALERT &#10; جزئیات تازه 🇮🇷",
    )
    assert "BREAKING" not in message
    assert "ALERT" not in message
    assert "@Middle_East_Spectator" not in message
    assert "&#10;" not in message
    assert "🇸🇦" not in message
    assert "🇮🇷" not in message
    assert "Middle East Spectator" not in message
    assert "Telegram" not in message
    assert "میدل ایست اسپکتیتور / تلگرام" in message


def test_hashtags_come_after_brand_footer_and_never_exceed_two():
    message = format_news(
        _item(title="missile drone explosion in Hormuz", summary="tanker attack and sanctions"),
        "موشک و پهپاد در تنگه هرمز",
        "گزارش انفجار نزدیک نفتکش منتشر شد",
    )
    tags = re.findall(r"(?<!\w)#[\w\u0600-\u06ff‌]+", message)
    assert 1 <= len(tags) <= 2
    assert message.rfind("مانیتور تحولات ایران") < message.rfind(tags[-1])
