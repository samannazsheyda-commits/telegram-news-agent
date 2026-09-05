from src.cars import format_car_prices, parse_car_prices


def test_parse_car_prices_keeps_every_source_row_and_exact_source_name():
    rows = [
        ("سایپا 151 GX", "1,275,000,000"),
        ("پژو 207 دنده‌ای هیدرولیک", "2,210,000,000"),
        ("تارا اتوماتیک V4 LX", "3,085,000,000"),
        ("سهند S", "1,510,000,000"),
        ("ری را", "4,070,000,000"),
        ("آریزو 5 FL", "3,700,000,000"),
        ("آریسان 2", "1,629,000,000"),
        ("مدل واقعی دیگر", "9,999,000,000"),
    ]
    html = "<table>" + "".join(
        f"<tr><td>{name}</td><td>{price}</td><td>0</td></tr>"
        for name, price in rows
    ) + "</table>"

    prices = parse_car_prices(html)

    assert [(p.name, p.market_toman) for p in prices] == [
        (name, int(price.replace(",", ""))) for name, price in rows
    ]
    assert all("پراید" not in p.name for p in prices)


def test_car_post_uses_exact_source_names_and_source_link():
    html = "<table>" + "".join(
        f"<tr><td>{name}</td><td>{1_000_000_000 + i * 10_000_000:,}</td></tr>"
        for i, name in enumerate([
            "سایپا 151 GX",
            "پژو 207 دنده‌ای هیدرولیک",
            "تارا اتوماتیک V4 LX",
            "سهند S",
            "ری را",
            "آریزو 5 FL",
            "آریسان 2",
            "مدل واقعی دیگر",
        ])
    ) + "</table>"
    prices = parse_car_prices(html)
    previous = {p.name: p.market_toman - 10_000_000 for p in prices}
    text = format_car_prices(prices, previous)

    assert "▲" in text
    assert "منبع: ماشین۳" in text
    assert "قیمت روز خودرو" in text
    assert "\n\n▫️" in text
    assert "سایپا 151 GX" in text
    assert "مدل واقعی دیگر" in text
    assert "پراید ۱۵۱" not in text
