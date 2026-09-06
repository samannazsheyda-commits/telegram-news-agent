import json

import src.phones as phones


def _row(name: str, price: int) -> str:
    return f'<tr><td>فروشگاه</td><td>تهران</td><td>امروز</td><td>{name}</td><td>{price:,}</td></tr>'


def _sample_html() -> str:
    apple = [
        'Apple iPhone 17 Pro Max', 'Apple iPhone 17 Pro', 'Apple iPhone 17 Air', 'Apple iPhone 17',
        'Apple iPhone 16 Pro Max', 'Apple iPhone 16 Pro', 'Apple iPhone 16 Plus', 'Apple iPhone 16',
        'Apple iPhone 15 Pro Max', 'Apple iPhone 15 Pro', 'Apple iPhone 15 Plus', 'Apple iPhone 15',
    ]
    samsung = [
        'Samsung Galaxy S26 Ultra', 'Samsung Galaxy S26+', 'Samsung Galaxy S26',
        'Samsung Galaxy Z Fold7', 'Samsung Galaxy Z Flip7', 'Samsung Galaxy S25 Ultra',
        'Samsung Galaxy S25+', 'Samsung Galaxy S25', 'Samsung Galaxy Z Fold6',
        'Samsung Galaxy Z Flip6', 'Samsung Galaxy S24 Ultra', 'Samsung Galaxy S24+',
    ]
    xiaomi = [
        'Xiaomi 17 Ultra', 'Xiaomi 17 Pro Max', 'Xiaomi 17 Pro', 'Xiaomi 17',
        'Xiaomi 15 Ultra', 'Xiaomi 15 Pro', 'Xiaomi 15', 'Xiaomi MIX Fold 5',
        'Xiaomi MIX Flip 2', 'Xiaomi 14 Ultra', 'Xiaomi 14 Pro', 'Xiaomi 14',
    ]
    other = [
        'Google Pixel 11 Pro XL', 'Google Pixel 11 Pro', 'Honor Magic8 Pro', 'OnePlus 14',
        'Huawei Pura 90 Ultra', 'Oppo Find X9 Ultra', 'vivo X300 Ultra', 'Nothing Phone (4) Pro',
        'Motorola Edge 70 Ultra', 'Sony Xperia 1 VIII', 'Google Pixel 10 Pro XL',
        'Honor Magic7 Pro', 'OnePlus 13', 'Huawei Mate 80 Pro', 'Oppo Find N6',
    ]
    names = apple + samsung + xiaomi + other
    return '<table>' + ''.join(_row(name, 100_000_000 + i * 1_000_000) for i, name in enumerate(names)) + '</table>'


def test_daily_phone_selection_is_exactly_40_in_brand_order_with_ten_iphones():
    selected = phones.parse_flagship_phone_prices(_sample_html())
    assert len(selected) == 40
    assert sum(x.name.startswith('Apple iPhone') for x in selected) == 10
    assert sum(x.name.startswith('Samsung ') for x in selected) == 10
    assert sum(x.name.startswith('Xiaomi ') for x in selected) == 10
    assert all(x.name.startswith('Apple iPhone') for x in selected[:10])
    assert all(x.name.startswith('Samsung ') for x in selected[10:20])
    assert all(x.name.startswith('Xiaomi ') for x in selected[20:30])
    assert not any(x.name.startswith(('Apple iPhone', 'Samsung ', 'Xiaomi ')) for x in selected[30:])


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
            return FakeResponse({'ok': True, 'result': {'access_token': 'phone-token'}})
        if url.endswith('/createPage'):
            return FakeResponse({'ok': True, 'result': {'url': 'https://telegra.ph/phone-prices-test'}})
        raise AssertionError(url)


def test_phone_list_creates_telegraph_instant_view_with_all_40_models():
    create_page = getattr(phones, 'create_phone_telegraph_page', None)
    assert callable(create_page), 'phone list must create a Telegraph Instant View page'

    prices = phones.parse_flagship_phone_prices(_sample_html())
    session = FakeSession()
    url = create_page(prices, session=session)
    assert url == 'https://telegra.ph/phone-prices-test'
    _, data, _ = session.posts[1]
    nodes = json.loads(data['content'])
    encoded = json.dumps(nodes, ensure_ascii=False)
    assert sum(item.name in encoded for item in prices) == 40
    assert encoded.index('آیفون') < encoded.index('سامسونگ') < encoded.index('شیائومی') < encoded.index('سایر برندها')


def test_compact_phone_post_links_to_instant_view_instead_of_dumping_40_rows():
    formatter = getattr(phones, 'format_phone_telegraph_post', None)
    assert callable(formatter), 'phone list needs a compact Telegram post formatter'
    text = formatter('https://telegra.ph/phone-prices-test', 40)
    assert '40' in text
    assert 'https://telegra.ph/phone-prices-test' in text
    assert 'مشاهده لیست کامل' in text
    assert 'mobile.ir' in text
    assert 'بی‌خبر' in text
