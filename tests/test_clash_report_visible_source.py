from src.final_output import finalize_telegram_message
from src.formatters import format_news
from src.sources import NewsItem


def test_clashreport_telegram_source_is_visible_as_clash_report_not_generic_source():
    item = NewsItem(
        "tg:clash:96729",
        "ClashReport / Telegram",
        "Wang Yi meets Abbas Araghchi in Beijing",
        "",
        "https://t.me/ClashReport/96729",
        "Wed, 16 Sep 2026 10:00:00 +0000",
    )

    message = finalize_telegram_message(
        format_news(
            item,
            "وانگ یی، وزیر امور خارجه چین، در پکن با عباس عراقچی دیدار کرد.",
            "",
            marker_override="⚪️",
        )
    )

    first_line = message.splitlines()[0]
    assert first_line.startswith("⚪️ <b>Clash Report:")
    assert "⚪️ <b>منبع:" not in first_line
