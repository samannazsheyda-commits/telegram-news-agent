import inspect

import src.runtime_v9 as v9
from src.cars import CarPrice


def test_production_car_formatter_creates_instant_view(monkeypatch):
    monkeypatch.setattr(v9, "create_car_telegraph_page", lambda prices, previous: "https://telegra.ph/car-test")
    text = v9._format_car_via_telegraph([CarPrice("تارا اتوماتیک V4 LX", 3_085_000_000)], {})
    assert "https://telegra.ph/car-test" in text
    assert "مشاهده لیست کامل" not in text


def test_production_installer_uses_telegraph_car_formatter():
    source = inspect.getsource(v9.install_persian_only_output)
    assert "format_car_prices = _format_car_via_telegraph" in source
    assert "_car_due_with_one_time_instant_republish" in source
