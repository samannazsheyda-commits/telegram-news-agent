from datetime import datetime, timezone

from src.formatters import format_market_daily_summary


def test_daily_summary_shows_only_current_price_and_percentage_change():
    text = format_market_daily_summary(
        first_usd=221_060,
        last_usd=227_205,
        first_gold=23_518_800,
        last_gold=23_674_400,
        now=datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc),
    )

    assert "۲۲۷,۲۰۵ تومان" in text
    assert "🔺 ۲.۷۸٪" in text
    assert "۲۳,۶۷۴,۴۰۰ تومان / گرم" in text
    assert "🔺 ۰.۶۶٪" in text
    assert "۲۲۱,۰۶۰" not in text
    assert "۲۳,۵۱۸,۸۰۰" not in text
    assert "۲۲۱,۰۶۰ ←" not in text
    assert "۲۳,۵۱۸,۸۰۰ ←" not in text
    assert "👉🏻" not in text


def test_daily_summary_uses_down_and_flat_symbols():
    text = format_market_daily_summary(
        first_usd=230_000,
        last_usd=227_700,
        first_gold=23_500_000,
        last_gold=23_500_000,
        now=datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc),
    )

    assert "🔻 ۱.۰۰٪" in text
    assert "➖ بدون تغییر" in text
