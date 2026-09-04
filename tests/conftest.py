import pytest


@pytest.fixture(autouse=True)
def isolate_external_daily_services(monkeypatch):
    import src.main as main

    # Existing unit tests should never make live HTTP calls. Feature-specific tests
    # can override these monkeypatches explicitly.
    monkeypatch.setattr(main, "fetch_news_detail", lambda item: item.summary)
    monkeypatch.setattr(main, "fetch_car_prices", lambda: (_ for _ in ()).throw(RuntimeError("car service disabled in unit tests")))
    monkeypatch.setattr(main, "fetch_weather_report", lambda: (_ for _ in ()).throw(RuntimeError("weather service disabled in unit tests")))
