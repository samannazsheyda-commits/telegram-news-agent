from datetime import datetime, timezone

from src.phones import (
    FlagshipPhonePrice,
    format_flagship_phone_prices,
    parse_flagship_phone_prices,
    phone_flagships_due,
)


def test_parse_flagships_picks_latest_series_and_lowest_listed_price():
    html = '''
    <table>
      <tr><td>Apple iPhone 16 Pro Max</td><td>392,000,000 تومان</td></tr>
      <tr><td>مشاهده فروشندگان</td><td>فروشگاه الف</td><td>تهران</td><td>امروز</td><td>Apple iPhone 17 Pro Max</td><td>489,900,000</td><td>نمودار قیمت</td></tr>
      <tr><td>مشاهده فروشندگان</td><td>فروشگاه ب</td><td>اصفهان</td><td>امروز</td><td>Apple iPhone 17 Pro Max</td><td>273,980,000</td><td>نمودار قیمت</td></tr>
      <tr><td>Samsung Galaxy S25 Ultra</td><td>210,000,000 تومان</td></tr>
      <tr><td>فروشگاه</td><td>تهران</td><td>امروز</td><td>Samsung Galaxy S26 Ultra</td><td>340,000,000</td></tr>
      <tr><td>فروشگاه</td><td>شیراز</td><td>امروز</td><td>Samsung Galaxy S26 Ultra</td><td>232,980,000</td></tr>
      <tr><td>Xiaomi 16 Ultra</td><td>190,000,000 تومان</td></tr>
      <tr><td>فروشگاه</td><td>امروز</td><td>Xiaomi 17 Ultra</td><td>280,000,000</td></tr>
      <tr><td>فروشگاه</td><td>امروز</td><td>Google Pixel 11 Pro XL</td><td>205,000,000</td></tr>
    </table>
    '''
    rows = parse_flagship_phone_prices(html)
    assert [(x.name, x.price_toman) for x in rows] == [
        ('Apple iPhone 17 Pro Max', 273_980_000),
        ('Samsung Galaxy S26 Ultra', 232_980_000),
        ('Xiaomi 17 Ultra', 280_000_000),
        ('Google Pixel 11 Pro XL', 205_000_000),
    ]


def test_phone_post_is_compact_and_has_bikhabaar_footer():
    text = format_flagship_phone_prices([
        FlagshipPhonePrice('Apple iPhone 17 Pro Max', 273_980_000),
        FlagshipPhonePrice('Samsung Galaxy S26 Ultra', 232_980_000),
    ])
    assert 'پرچمدارهای موبایل' in text
    assert '273,980,000' in text
    assert '232,980,000' in text
    assert 'mobile.ir' in text
    assert 'بی‌خبر' in text
    assert 'هوا' not in text
    assert 'دما' not in text


def test_flagship_phone_post_is_due_once_daily_after_noon_tehran():
    before = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)   # 11:30 Tehran
    after = datetime(2026, 9, 6, 8, 30, tzinfo=timezone.utc)   # 12:00 Tehran
    assert phone_flagships_due({}, before) is False
    assert phone_flagships_due({}, after) is True
    assert phone_flagships_due({'phone_flagships_last_sent_date': '2026-09-06'}, after) is False
