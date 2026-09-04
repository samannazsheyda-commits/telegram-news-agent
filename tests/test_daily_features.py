from datetime import datetime, timezone

import src.main as main
from src.cars import CarPrice
from src.sources import NewsItem, TruthPost


def _base_state(extra=""):
    body = '{"truth_last_id":"10","news_seen":["seed"],"market_last_sent_at":"2026-09-04T06:00:00+00:00"'
    if extra:
        body += "," + extra
    return body + "}"


def _quiet_news(monkeypatch):
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("market disabled in this unit test")))


def test_car_prices_send_once_at_11_tehran(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(_base_state('"weather_noon_last_sent_date":"2026-09-04"'), encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token"); monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _quiet_news(monkeypatch)
    monkeypatch.setattr(main, "fetch_car_prices", lambda: [CarPrice("پژو ۲۰۷ اتومات", 2_800_000_000)])
    monkeypatch.setattr(main, "format_car_prices", lambda prices, previous: "CAR\n📌 منبع")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    now = datetime(2026, 9, 4, 7, 30, tzinfo=timezone.utc)
    assert main.run(now) == 0
    assert sent == ["CAR\n📌 منبع"]
    assert main.load_state(state_path)["car_last_sent_date"] == "2026-09-04"
    assert main.run(now) == 0
    assert sent == ["CAR\n📌 منبع"]


def test_noon_weather_sends_once_at_12_tehran(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(_base_state('"car_last_sent_date":"2026-09-04"'), encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token"); monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _quiet_news(monkeypatch)
    monkeypatch.setattr(main, "fetch_weather_report", lambda: object())
    monkeypatch.setattr(main, "format_noon_weather", lambda report: "NOON WEATHER\n📌 Open-Meteo")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    now = datetime(2026, 9, 4, 8, 30, tzinfo=timezone.utc)
    assert main.run(now) == 0
    assert sent == ["NOON WEATHER\n📌 Open-Meteo"]
    assert main.load_state(state_path)["weather_noon_last_sent_date"] == "2026-09-04"


def test_night_weather_sends_at_22_tehran(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(_base_state('"car_last_sent_date":"2026-09-04","weather_noon_last_sent_date":"2026-09-04","market_last_sent_at":"2026-09-04T17:00:00+00:00"'), encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token"); monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _quiet_news(monkeypatch)
    monkeypatch.setattr(main, "fetch_weather_report", lambda: object())
    monkeypatch.setattr(main, "format_night_weather", lambda report: "NIGHT WEATHER\n📌 Open-Meteo")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    now = datetime(2026, 9, 4, 18, 30, tzinfo=timezone.utc)
    assert main.run(now) == 0
    assert sent == ["NIGHT WEATHER\n📌 Open-Meteo"]
    assert main.load_state(state_path)["weather_night_last_sent_date"] == "2026-09-04"


def test_midnight_market_summary_uses_previous_days_first_and_last_prices(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        _base_state('"market_day_prices":{"date":"2026-09-04","first_usd":200000,"last_usd":210000,"first_gold":20000000,"last_gold":19000000},"car_last_sent_date":"2026-09-04","weather_noon_last_sent_date":"2026-09-04","weather_night_last_sent_date":"2026-09-04"'),
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token"); monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _quiet_news(monkeypatch)
    monkeypatch.setattr(main, "format_market_daily_summary", lambda *args: "DAILY MARKET\n📌 TGJU")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    now = datetime(2026, 9, 4, 20, 30, tzinfo=timezone.utc)
    assert main.run(now) == 0
    assert sent == ["DAILY MARKET\n📌 TGJU"]
    assert main.load_state(state_path)["market_daily_summary_last_date"] == "2026-09-04"


def test_every_distinct_trump_statement_about_iran_bypasses_importance_filter(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(_base_state('"car_last_sent_date":"2026-09-04","weather_noon_last_sent_date":"2026-09-04"'), encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token"); monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("market disabled")))
    items = [
        NewsItem("t1", "Reuters", "Trump says he spoke about Iran this morning", "The president described the conversation without announcing a new policy.", "https://n/1", "Fri, 04 Sep 2026 09:00:00 GMT"),
        NewsItem("t2", "CNN", "Trump says Iran remains on his agenda", "He made the comment later in the day.", "https://n/2", "Fri, 04 Sep 2026 09:20:00 GMT"),
    ]
    monkeypatch.setattr(main, "fetch_news_items", lambda: items)
    monkeypatch.setattr(main, "fetch_news_detail", lambda item: item.summary)
    monkeypatch.setattr(main, "translate_to_fa", lambda text: text)
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    assert main.run(datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)) == 0
    news = [x for x in sent if "لینک منبع خبر" in x]
    assert len(news) == 2
    assert any("spoke about Iran" in x for x in news)
    assert any("Iran remains" in x for x in news)
