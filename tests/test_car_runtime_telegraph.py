import inspect

import src.runtime_v9 as v9
from src.cars import CarPrice


def test_production_car_formatter_stays_inside_telegram():
    formatter = getattr(v9, "_format_car_for_telegram", None)
    assert callable(formatter), "production car formatter must render a native Telegram post"

    text = formatter([CarPrice("تارا اتوماتیک V4 LX", 3_085_000_000)], {})

    assert "تارا اتوماتیک V4 LX" in text
    assert "3,085,000,000 تومان" in text
    assert "telegra.ph" not in text
    assert "مشاهده لیست کامل قیمت خودروها" not in text


def test_production_installer_uses_native_car_formatter_not_telegraph():
    source = inspect.getsource(v9.install_persian_only_output)
    assert "format_car_prices = _format_car_for_telegram" in source
    assert "format_car_prices = _format_car_via_telegraph" not in source
