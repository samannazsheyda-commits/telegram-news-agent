from datetime import datetime, timezone

import src.main as main
from src.sources import NewsItem


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def _item(key: str, title: str = "Iran missile attack confirmed") -> NewsItem:
    return NewsItem(
        key,
        "Reuters",
        title,
        "Officials confirmed the Iran-related security development.",
        f"https://example.com/{key}",
        "Sun, 06 Sep 2026 11:00:00 GMT",
    )


def _configure(tmp_path, monkeypatch, items):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"truth_last_id":"10","news_seen":["seed"],"market_last_sent_at":"2026-09-06T11:30:00+00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [])
    monkeypatch.setattr(main, "fetch_news_items", lambda: list(items))
    monkeypatch.setattr(main, "_car_due", lambda state, now: False)
    monkeypatch.setattr(main, "_weather_noon_due", lambda state, now: False)
    monkeypatch.setattr(main, "_weather_night_due", lambda state, now: False)
    monkeypatch.setattr(main, "_market_summary_day", lambda state, now: None)
    monkeypatch.setattr(main, "_market_quiet_hours", lambda now: True)
    monkeypatch.setattr(main, "translate_to_fa", lambda text: "ترجمه فارسی")
    monkeypatch.setattr(main, "fetch_news_detail", lambda item: "")
    return state_path


def test_empty_formatted_news_is_not_marked_seen(tmp_path, monkeypatch):
    item = _item("format-empty")
    state_path = _configure(tmp_path, monkeypatch, [item])
    monkeypatch.setattr(main, "_select_top_stories", lambda candidates, references: (candidates, []))
    monkeypatch.setattr(main, "format_news", lambda *args, **kwargs: "")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    assert main.run(NOW) == 0
    assert sent == []
    assert item.key not in main.load_state(state_path)["news_seen"]


def test_formatter_failure_does_not_starve_later_story(tmp_path, monkeypatch):
    first = _item("bad-format")
    second = _item("good-format")
    state_path = _configure(tmp_path, monkeypatch, [first, second])
    monkeypatch.setattr(main, "_select_top_stories", lambda candidates, references: ([second, first], []))

    def formatter(item, *args, **kwargs):
        if item.key == first.key:
            raise ValueError("bad formatter input")
        return "خبر دوم"

    monkeypatch.setattr(main, "format_news", formatter)
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    assert main.run(NOW) == 0
    assert sent == ["خبر دوم"]
    seen = main.load_state(state_path)["news_seen"]
    assert first.key not in seen
    assert second.key in seen


def test_send_failure_does_not_mark_failed_story_seen_or_starve_later_story(tmp_path, monkeypatch):
    first = _item("send-fails")
    second = _item("send-works")
    state_path = _configure(tmp_path, monkeypatch, [first, second])
    monkeypatch.setattr(main, "_select_top_stories", lambda candidates, references: ([second, first], []))
    monkeypatch.setattr(main, "format_news", lambda item, *args, **kwargs: item.key)
    sent = []

    def sender(text, token, chat):
        if text == first.key:
            raise RuntimeError("telegram rejected one message")
        sent.append(text)

    monkeypatch.setattr(main, "send_telegram", sender)

    assert main.run(NOW) == 0
    assert sent == [second.key]
    seen = main.load_state(state_path)["news_seen"]
    assert first.key not in seen
    assert second.key in seen


def test_retryable_ingestion_rejections_are_not_marked_seen(tmp_path, monkeypatch):
    missing_time = _item("missing-time")
    missing_link = _item("missing-link")
    state_path = _configure(tmp_path, monkeypatch, [missing_time, missing_link])

    def reason(item, now):
        return "invalid_publish_time" if item.key == missing_time.key else "missing_direct_source_link"

    monkeypatch.setattr(main, "_news_rejection_reason", reason)
    monkeypatch.setattr(main, "send_telegram", lambda *args, **kwargs: None)

    assert main.run(NOW) == 0
    seen = main.load_state(state_path)["news_seen"]
    assert missing_time.key not in seen
    assert missing_link.key not in seen


def test_empty_seen_state_processes_current_news_instead_of_silently_bootstrapping(tmp_path, monkeypatch):
    item = _item("first-current")
    state_path = _configure(tmp_path, monkeypatch, [item])
    state_path.write_text(
        '{"truth_last_id":"10","news_seen":[],"market_last_sent_at":"2026-09-06T11:30:00+00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "_select_top_stories", lambda candidates, references: (candidates, []))
    monkeypatch.setattr(main, "format_news", lambda *args, **kwargs: "خبر جاری")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    assert main.run(NOW) == 0
    assert sent == ["خبر جاری"]
    assert item.key in main.load_state(state_path)["news_seen"]

# Regression suite for transactional news delivery; do not convert retryable failures into seen items.
