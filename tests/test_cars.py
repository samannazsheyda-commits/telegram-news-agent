from src.cars import format_car_prices, parse_car_prices


def test_parse_target_car_prices_from_market_table():
    rows = [
        ("پژو 207 دنده‌ای (برقی)", "2,210,000,000"),
        ("پژو 207 اتوماتیک", "2,810,000,000"),
        ("دنا پلاس اتوماتیک", "3,230,000,000"),
        ("دنا پلاس MT6", "2,440,000,000"),
        ("تارا دستی V1", "2,275,000,000"),
        ("تارا اتوماتیک V4", "3,085,000,000"),
        ("سورن پلاس XU7P", "1,800,000,000"),
        ("رانا پلاس", "1,750,000,000"),
        ("شاهین G", "2,100,000,000"),
        ("شاهین اتوماتیک", "2,350,000,000"),
        ("کوییک GX", "1,050,000,000"),
        ("ساینا S", "1,020,000,000"),
        ("اطلس G", "1,250,000,000"),
        ("سهند S", "1,150,000,000"),
        ("پژو پارس XU7P", "1,900,000,000"),
    ]
    html = "<table>" + "".join(f"<tr><td>{n}</td><td>{p}</td><td>0</td></tr>" for n, p in rows) + "</table>"
    prices = parse_car_prices(html)
    assert len(prices) == 15
    assert prices[0].name == "پژو ۲۰۷ دنده‌ای"
    assert prices[0].market_toman == 2_210_000_000
    assert prices[-1].name == "پژو پارس XU7P"


def test_car_post_has_change_and_source():
    html = "<table>" + "".join(
        f"<tr><td>{name}</td><td>{1_000_000_000 + i * 10_000_000:,}</td></tr>"
        for i, name in enumerate([
            "پژو 207 دنده‌ای (برقی)", "پژو 207 اتوماتیک", "دنا پلاس اتوماتیک", "دنا پلاس MT6",
            "تارا دستی V1", "تارا اتوماتیک V4", "سورن پلاس XU7P", "رانا پلاس",
            "شاهین G", "شاهین اتوماتیک", "کوییک GX", "ساینا S", "اطلس G", "سهند S", "پژو پارس XU7P",
        ])
    ) + "</table>"
    prices = parse_car_prices(html)
    previous = {p.name: p.market_toman - 10_000_000 for p in prices}
    text = format_car_prices(prices, previous)
    assert "▲" in text
    assert "منبع: ماشین۳" in text
    assert "قیمت روز خودرو" in text
