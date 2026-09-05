from src import runtime_v2 as v2
from src import runtime_v5 as v5
from src.sources import NewsItem


def test_runtime_v5_keeps_configured_custom_sources_connected(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(v2, "_original_custom_fetch", lambda: [sentinel])
    monkeypatch.setattr(v5, "_fresh_x_installed", False)

    v5.install_fresh_x_policy()

    assert v2._original_custom_fetch() == [sentinel]


def test_custom_telegram_reference_enters_runtime_feed(monkeypatch):
    telegram_item = NewsItem(
        "tg:1",
        "تبز لایو / Telegram",
        "Iran security update",
        "Iran security update",
        "https://t.me/tabzlive/1",
        "Fri, 05 Sep 2026 14:00:00 GMT",
    )
    monkeypatch.setattr(v2, "_fetch_preserved_special_items", lambda: [])
    monkeypatch.setattr(v2, "_original_custom_fetch", lambda: [telegram_item])

    assert v2._custom_x_and_alert_items() == [telegram_item]
