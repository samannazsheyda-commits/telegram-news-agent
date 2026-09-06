from datetime import datetime, timezone

import src.main as main
from src.cars import CarPrice
from src.sources import TruthPost


def test_daily_car_post_uses_telegraph_page_not_full_external_list(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"truth_last_id":"10","news_seen":["seed"],"weather_noon_last_sent_date":"2026-09-06","market_last_sent_at":"2026-09-06T06:00:00+00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("market disabled")))
    monkeypatch.setattr(main, "fetch_car_prices", lambda: [CarPrice("تارا اتوماتیک V4 LX", 3_085_000_000)])

    created = []
    monkeypatch.setattr(
        main,
        "create_car_telegraph_page",
        lambda prices, previous: created.append((prices, previous)) or "https://telegra.ph/car-prices-today",
        raising=False,
    )
    monkeypatch.setattr(
        main,
        "format_car_telegraph_post",
        lambda url, count: f"CAR TELEGRAPH {count} {url}",
        raising=False,
    )
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    now = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)  # 11:30 Tehran
    assert main.run(now) == 0
    assert created
    assert sent == ["CAR TELEGRAPH 1 https://telegra.ph/car-prices-today"]
    assert "mashin3.com" not in sent[0]
