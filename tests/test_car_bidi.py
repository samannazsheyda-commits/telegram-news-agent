from src.cars import CarPrice, format_car_prices


def test_mixed_persian_latin_model_name_is_directionally_isolated():
    text = format_car_prices([CarPrice("شاهین G", 2_285_000_000)])
    assert "\u2067<b>شاهین G</b>\u2069:" in text


def test_multi_token_latin_suffix_stays_attached_to_source_name():
    text = format_car_prices([CarPrice("تارا اتوماتیک V4 LX", 3_085_000_000)])
    assert "\u2067<b>تارا اتوماتیک V4 LX</b>\u2069:" in text
