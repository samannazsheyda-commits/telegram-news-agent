import pytest


@pytest.fixture(autouse=True)
def isolate_external_daily_services(monkeypatch, tmp_path):
    import src.main as main
    import src.runtime as runtime
    from src.editorial_store import LocalEditorialStore

    # Unit tests must never read or mutate production runtime state tracked in the repo.
    monkeypatch.setattr(main, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(
        runtime,
        "_store",
        LocalEditorialStore(tmp_path / "editorial_queue.json", tmp_path / "editorial_history.json"),
    )
    monkeypatch.setattr(runtime, "_sent_news_items", [])

    # Existing unit tests should never make live HTTP calls. Feature-specific tests
    # can override these monkeypatches explicitly.
    monkeypatch.setattr(main, "fetch_news_detail", lambda item: item.summary)
    monkeypatch.setattr(main, "fetch_car_prices", lambda: (_ for _ in ()).throw(RuntimeError("car service disabled in unit tests")))
    monkeypatch.setattr(main, "fetch_weather_report", lambda: (_ for _ in ()).throw(RuntimeError("weather service disabled in unit tests")))
