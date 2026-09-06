from datetime import datetime, timezone
import json

from src import cars, phones
from src import runtime_v9 as v9
from src import runtime_v10 as v10


NOW = datetime(2026, 9, 6, 14, 18, tzinfo=timezone.utc)  # 17:48 Tehran


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, page_url):
        self.page_url = page_url
        self.posts = []

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, data, timeout))
        if url.endswith('/createAccount'):
            return FakeResponse({'ok': True, 'result': {'access_token': 'token'}})
        if url.endswith('/createPage'):
            return FakeResponse({'ok': True, 'result': {'url': self.page_url}})
        raise AssertionError(url)


def test_phone_page_uses_persian_jalali_title_time_digits_and_never_shows_missing_price_text():
    prices = [
        phones.FlagshipPhonePrice(
            'Apple iPhone 17 Pro Max', 300_000_000,
            registered_toman=439_980_000,
            unregistered_toman=300_000_000,
        ),
        phones.FlagshipPhonePrice(
            'Samsung Galaxy S26 Ultra', 250_000_000,
            registered_toman=None,
            unregistered_toman=250_000_000,
        ),
        phones.FlagshipPhonePrice(
            'Xiaomi 17 Ultra', 0,
            registered_toman=None,
            unregistered_toman=None,
        ),
    ]
    session = FakeSession('https://telegra.ph/phone-fa-test')
    phones.create_phone_telegraph_page(prices, session=session, now=NOW)
    _, data, _ = session.posts[1]
    assert data['title'] == 'قیمت روز موبایل | ۱۵ شهریور ۱۴۰۵'
    encoded = json.dumps(json.loads(data['content']), ensure_ascii=False)
    assert 'آخرین به‌روزرسانی: ۱۵ شهریور ۱۴۰۵، ساعت ۱۷:۴۸' in encoded
    assert 'Apple iPhone 17 Pro Max' in encoded
    assert '۴۳۹,۹۸۰,۰۰۰ تومان' in encoded
    assert '۳۰۰,۰۰۰,۰۰۰ تومان' in encoded
    assert 'Samsung Galaxy S26 Ultra' in encoded
    assert '۲۵۰,۰۰۰,۰۰۰ تومان' in encoded
    assert 'Xiaomi 17 Ultra' not in encoded
    assert 'در منبع ثبت نشده' not in encoded
    assert 'در فهرست قیمت روز موبایل' in encoded


def test_car_page_uses_persian_jalali_title_time_and_price_digits_while_model_name_stays_exact():
    prices = [
        cars.CarPrice('تارا اتوماتیک V4 LX', 3_085_000_000),
        cars.CarPrice('شاهین G', 2_285_000_000),
    ]
    session = FakeSession('https://telegra.ph/car-fa-test')
    cars.create_car_telegraph_page(prices, {}, session=session, now=NOW)
    _, data, _ = session.posts[1]
    assert data['title'] == 'قیمت روز خودرو | ۱۵ شهریور ۱۴۰۵'
    encoded = json.dumps(json.loads(data['content']), ensure_ascii=False)
    assert 'آخرین به‌روزرسانی: ۱۵ شهریور ۱۴۰۵، ساعت ۱۷:۴۸' in encoded
    assert 'تارا اتوماتیک V4 LX' in encoded
    assert '۳,۰۸۵,۰۰۰,۰۰۰ تومان' in encoded
    assert 'در فهرست قیمت روز خودرو' in encoded


def test_telegram_titles_also_include_today_persian_date():
    phone = phones.format_phone_telegraph_post('https://telegra.ph/phone-fa-test', 12, now=NOW)
    car = cars.format_car_telegraph_post('https://telegra.ph/car-fa-test', 102, now=NOW)
    assert 'قیمت روز موبایل | ۱۵ شهریور ۱۴۰۵' in phone
    assert 'قیمت روز خودرو | ۱۵ شهریور ۱۴۰۵' in car


def test_latest_redesign_forces_each_price_post_once_more_today():
    car_state = {'car_last_sent_date': '2026-09-06', 'car_instant_republish_fresh_2_date': '2026-09-06'}
    assert v9._car_due_with_persian_page_republish(car_state, NOW) is True
    assert v9._car_due_with_persian_page_republish(car_state, NOW) is False

    phone_state = {
        'phone_flagships_last_sent_date': '2026-09-06',
        'phone_flagships_fresh_republish_2_date': '2026-09-06',
    }
    assert v10._phone_flagships_due_with_persian_page_republish(phone_state, NOW) is True
    assert v10._phone_flagships_due_with_persian_page_republish(phone_state, NOW) is False
