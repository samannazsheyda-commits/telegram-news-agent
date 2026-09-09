from src.formatters import _clean_persian_output_text, _source_label, format_news
from src.sources import NewsItem


def _item(source="RN Intel / Telegram", title="Missile alert in Saudi Arabia", summary="Alert in Saudi Arabia"):
    return NewsItem(
        key="x",
        source=source,
        title=title,
        summary=summary,
        link="https://example.com/x",
        published="Wed, 09 Sep 2026 14:30:00 +0000",
    )


def test_source_labels_render_fully_persian():
    assert _source_label("RN Intel / Telegram") == "آر‌اِن اینتل / تلگرام"
    assert _source_label("Jerusalem Post / X") == "جروزالم پست / ایکس"
    assert _source_label("Middle East Spectator / Telegram") == "میدل ایست اسپکتیتور / تلگرام"


def test_editor_repairs_known_bad_persian_and_latin_labels():
    cleaned = _clean_persian_output_text("BREAKING: خب خب، ALERT از @foo در Telegram")
    assert "BREAKING" not in cleaned
    assert "ALERT" not in cleaned
    assert "Telegram" not in cleaned
    assert "@foo" not in cleaned
    assert "خوب خوب" in cleaned
    assert "فوری" in cleaned
    assert "هشدار" in cleaned
    assert "تلگرام" in cleaned


def test_flags_are_only_at_the_end_of_production_news_card():
    from src import runtime_v7 as v7

    message = v7._format_news_with_footer_icons(
        _item(),
        "هشدار موشکی در عربستان سعودی",
        "پدافند هوایی عربستان در آماده‌باش قرار گرفته است",
    )
    lines = [line for line in message.splitlines() if line.strip()]
    flag_lines = [i for i, line in enumerate(lines) if "🇸🇦" in line]
    assert flag_lines == [len(lines) - 1]
    assert "🇸🇦" not in lines[0]


def test_final_post_has_no_known_english_transport_labels():
    message = format_news(
        _item(source="Middle East Spectator / Telegram"),
        "فوری: هشدار در عربستان سعودی",
        "سامانه‌های پدافندی در آماده‌باش قرار گرفته‌اند",
    )
    for token in ("Middle East Spectator", "Telegram", "BREAKING", "ALERT"):
        assert token not in message
