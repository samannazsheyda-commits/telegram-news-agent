from src.custom_sources import parse_public_telegram_channel
from src.services import _repair_news_idioms
from src.sources import NewsItem


def test_telegram_source_suffix_is_persian():
    html = '''
    <div class="tgme_widget_message" data-post="GeoPWatch/123">
      <div class="tgme_widget_message_text">Iran tanker movement near Hormuz</div>
      <time datetime="2026-09-05T16:00:00+00:00"></time>
    </div>
    '''
    items = parse_public_telegram_channel(html, "GeoPWatch", "ژئوپی واچ")
    assert len(items) == 1
    assert items[0].source == "ژئوپی واچ / تلگرام"


def test_hormuz_tanker_machine_translation_is_repaired_precisely():
    source = "🇺🇸 ❌ 🇮🇷 - 5 tankers above the Strait of Hormuz. 3 from Qatar, 2 from Israel."
    translated = "🇺🇸 ❌ 🇮🇷 - ۵ نفتکش بالای تنگه هرمز. ۳ تا از قطر، ۲ تا از اسرائیل."
    repaired = _repair_news_idioms(source, translated)
    assert repaired == "۵ نفتکش در محدوده تنگه هرمز؛ ۳ نفتکش از قطر و ۲ نفتکش از اسرائیل."


def test_news_card_keeps_visual_emojis_at_bottom_only(monkeypatch):
    from src import runtime_v7 as v7

    item = NewsItem(
        "tg:1",
        "ژئوپی واچ / تلگرام",
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
    assert first_line.startswith("<b>ژئوپی واچ / تلگرام:")
    assert "⚪️" not in text
    assert "🇺🇸" not in first_line
    assert "🇮🇷" not in first_line
    assert text.rstrip().splitlines()[-1].strip().startswith("🇺🇸")
    assert "🚢" in text.rstrip().splitlines()[-1]
    assert "⚓" in text.rstrip().splitlines()[-1]
