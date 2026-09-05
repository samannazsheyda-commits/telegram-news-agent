from datetime import datetime, timezone

from src.sources import NewsItem


def _item(source, title, summary=""):
    return NewsItem(
        "k",
        source,
        title,
        summary,
        "https://t.me/example/1" if "Telegram" in source else "https://x.com/Reuters/status/1",
        "Sat, 05 Sep 2026 17:00:00 +0000",
    )


def test_telegram_editor_uses_full_summary_instead_of_cut_title(monkeypatch):
    from src import runtime_v7 as v7

    item = _item(
        "Clash Report / Telegram",
        "John Bolton on Iran: I think the US and Israeli strikes...",
        "John Bolton on Iran: I think regime change is necessary. I think the US and Israeli strikes weakened Tehran.",
    )
    monkeypatch.setattr(v7, "_original_translate", lambda value, session=None: "جان بولتون درباره ایران گفت تغییر حکومت را ضروری می‌داند. او گفت حملات آمریکا و اسرائیل تهران را تضعیف کرده است.")
    v7._translation_cache.clear()
    edited = v7._edited_title(item)
    assert edited.endswith("است.")
    assert "..." not in edited


def test_promotional_x_post_is_rejected():
    from src import runtime_v7 as v7

    item = NewsItem(
        "x:FT:1",
        "Financial Times / X",
        "Catch their FT Weekend Festival session about Iran and the US military",
        "",
        "https://x.com/FT/status/1",
        "Sat, 05 Sep 2026 17:00:00 +0000",
    )
    assert v7._easy_rejection_reason(item, datetime(2026, 9, 5, 17, 10, tzinfo=timezone.utc)) == "promotional_or_non_news"


def test_ordinary_news_has_no_white_circle_and_telegram_is_persian(monkeypatch):
    from src import runtime_v7 as v7

    item = _item("Clash Report / Telegram", "Iran says talks continue")
    monkeypatch.setattr(v7.v2, "_original_news_format", lambda item, title, summary, marker_override=None: f"⚪️ <b>{item.source}: {title}</b>\n\n⏰ زمان\n📌 لینک")
    monkeypatch.setattr(v7, "_country_flags", lambda *args: "🇮🇷")
    monkeypatch.setattr(v7, "_topic_icons", lambda *args: "🕊️")
    rendered = v7._format_news_with_footer_icons(item, "ایران اعلام کرد مذاکرات ادامه دارد.", "")
    assert not rendered.startswith("⚪️")
    assert "/ تلگرام" in rendered
    assert "/ Telegram" not in rendered
    assert rendered.splitlines()[-1] == "🇮🇷 🕊️"
