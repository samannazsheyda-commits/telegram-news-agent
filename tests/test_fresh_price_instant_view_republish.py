from datetime import datetime, timezone
import inspect

from src import cars, phones
from src import runtime_v9 as v9
from src import runtime_v10 as v10


def test_phone_parser_keeps_registered_and_unregistered_prices_separately():
    html = '''<table>
    <tr><td>Apple iPhone 17</td><td>210,000,000</td><td>بدون رجیستر</td></tr>
    <tr><td>Apple iPhone 17</td><td>319,000,000</td><td>با رجیستر ۲۵۶</td></tr>
    </table>'''
    item = phones.parse_flagship_phone_prices(html)[0]
    assert item.unregistered_toman == 210_000_000
    assert item.registered_toman == 319_000_000


def test_phone_instant_view_starts_with_banner_and_shows_both_registry_states():
    item = phones.FlagshipPhonePrice(
        'Apple iPhone 17', 210_000_000,
        registered_toman=319_000_000,
        unregistered_toman=210_000_000,
    )
    nodes = phones._telegraph_phone_nodes([item])
    assert nodes[0]['tag'] == 'figure'
    encoded = str(nodes)
    assert 'با رجیستر' in encoded
    assert 'بدون رجیستر' in encoded


def test_phone_telegram_card_uses_linked_title_without_separate_view_link():
    text = phones.format_phone_telegraph_post('https://telegra.ph/phone-test', 40)
    assert 'https://telegra.ph/phone-test' in text
    assert 'مشاهده لیست کامل' not in text
    assert 'لیست 40 مدل' not in text


def test_car_production_formatter_is_instant_view_again():
    source = inspect.getsource(v9.install_persian_only_output)
    assert 'format_car_prices = _format_car_via_telegraph' in source
    text = cars.format_car_telegraph_post('https://telegra.ph/car-test', 102)
    assert 'https://telegra.ph/car-test' in text
    assert 'مشاهده لیست کامل' not in text
    assert 'لیست کامل قیمت' not in text


def test_fresh_car_and_phone_republish_are_each_forced_only_once_today():
    now = datetime(2026, 9, 6, 13, 30, tzinfo=timezone.utc)

    car_state = {'car_last_sent_date': '2026-09-06', 'car_native_republish_date': '2026-09-06'}
    assert v9._car_due_with_one_time_instant_republish(car_state, now) is True
    assert v9._car_due_with_one_time_instant_republish(car_state, now) is False

    phone_state = {
        'phone_flagships_last_sent_date': '2026-09-06',
        'phone_flagships_republish_40_date': '2026-09-06',
    }
    assert v10._phone_flagships_due_with_fresh_republish(phone_state, now) is True
    assert v10._phone_flagships_due_with_fresh_republish(phone_state, now) is False
