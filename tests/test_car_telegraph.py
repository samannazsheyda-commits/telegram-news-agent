import json

from src.cars import (
    CAR_BANNER_URL,
    CAR_PRICE_URL,
    CarPrice,
    create_car_telegraph_page,
    format_car_telegraph_post,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.posts = []

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, data, timeout))
        if url.endswith('/createAccount'):
            return FakeResponse({'ok': True, 'result': {'access_token': 'token-1'}})
        if url.endswith('/createPage'):
            return FakeResponse({'ok': True, 'result': {'url': 'https://telegra.ph/car-prices-test'}})
        raise AssertionError(url)


def test_telegraph_page_contains_banner_and_every_exact_source_row():
    prices = [
        CarPrice('سایپا 151 GX', 1_275_000_000),
        CarPrice('شاهین G', 2_285_000_000),
        CarPrice('تارا اتوماتیک V4 LX', 3_085_000_000),
    ]
    previous = {'سایپا 151 GX': 1_265_000_000, 'شاهین G': 2_285_000_000}
    session = FakeSession()

    url = create_car_telegraph_page(prices, previous, session=session)

    assert url == 'https://telegra.ph/car-prices-test'
    _, data, _ = session.posts[1]
    nodes = json.loads(data['content'])
    encoded = json.dumps(nodes, ensure_ascii=False)
    assert CAR_BANNER_URL in encoded
    assert 'سایپا 151 GX' in encoded
    assert 'شاهین G' in encoded
    assert 'تارا اتوماتیک V4 LX' in encoded
    assert 'پراید' not in encoded
    assert '▲' in encoded
    assert 'بدون تغییر' in encoded
    assert CAR_PRICE_URL in encoded
    assert 'نام مدل‌ها عیناً مطابق منبع نمایش داده می‌شوند' not in encoded


def test_compact_telegram_post_links_to_full_telegraph_page():
    text = format_car_telegraph_post('https://telegra.ph/car-prices-test', 42)

    assert 'قیمت روز خودرو' in text
    assert '42' in text
    assert 'https://telegra.ph/car-prices-test' in text
    assert 'مشاهده لیست کامل قیمت خودروها' in text
    assert 'منبع: ماشین۳' in text
