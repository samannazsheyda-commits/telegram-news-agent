from src.sources import NewsItem


def test_hormuz_tanker_machine_translation_is_repaired_precisely():
    from src import runtime_v7 as v7

    source = "🇺🇸 ❌ 🇮🇷 - 5 tankers above the Strait of Hormuz. 3 from Qatar, 2 from Israel."
    translated = "🇺🇸 ❌ 🇮🇷 - ۵ نفتکش بالای تنگه هرمز. ۳ تا از قطر، ۲ تا از اسرائیل."
    repaired = v7._repair_precise_translation(source, translated)
    assert repaired == "۵ نفتکش در محدوده تنگه هرمز؛ ۳ نفتکش از قطر و ۲ نفتکش از اسرائیل."


def test_news_card_uses_persian_telegram_label_and_keeps_visual_emojis_at_bottom_only():
    from src import runtime_v7 as v7

    item = NewsItem(
        "tg:1",
        "ژئوپی واچ / Telegram",
        "🇺🇸 ❌ 🇮🇷 - 5 tankers above the Strait of Hormuz. 3 from Qatar, 2 from Israel.",
        "",
        "https://t.me/GeoPWatch/123",
        "Sat, 05 Sep 2026 16:00:00 +0000",
    )
    text = v7._format_news_with_footer_icons(
        item,
        "🇺🇸 ❌ 🇮🇷 - ۵ نفتکش در محدوده تنگه هرمز؛ ۳ نفتکش از قطر و ۲ نفتکش از اسرائیل.",
        "",
        marker_override="⚪️",
    )
    first_line = text.splitlines()[0]
    bottom = text.rstrip().splitlines()[-1].strip()
    assert first_line.startswith("<b>ژئوپی واچ / تلگرام:")
    assert "Telegram" not in text
    assert "⚪️" not in text
    assert "🇺🇸" not in first_line
    assert "🇮🇷" not in first_line
    assert bottom.startswith("🇺🇸")
    assert "🇮🇷" in bottom
    assert "🇶🇦" in bottom
    assert "🇮🇱" in bottom
    assert "🚢" in bottom
    assert "⚓" in bottom


def test_critical_marker_moves_to_bottom_instead_of_headline():
    from src import runtime_v7 as v7

    item = NewsItem(
        "tg:2",
        "کلش ریپورت / Telegram",
        "Iran missile attack reported near Tehran",
        "",
        "https://t.me/ClashReport/456",
        "Sat, 05 Sep 2026 16:00:00 +0000",
    )
    text = v7._format_news_with_footer_icons(
        item,
        "حمله موشکی در نزدیکی تهران گزارش شده است.",
        "",
        marker_override="🛑",
    )
    assert not text.splitlines()[0].startswith("🛑")
    assert "🛑" in text.rstrip().splitlines()[-1]
