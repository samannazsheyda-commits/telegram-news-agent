from datetime import datetime, timezone

import src.main as main
from src.sources import NewsItem, TruthPost


def _item(key: str, minute: int, title: str) -> NewsItem:
    return NewsItem(
        key,
        "Reuters",
        title,
        "",
        f"https://example.com/{key}",
        f"Sat, 05 Sep 2026 08:{minute:02d}:00 GMT",
    )


def _prepare(tmp_path, monkeypatch, items):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"truth_last_id":"10","news_seen":["seed"],"market_last_sent_at":"2026-09-05T08:30:00+00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: items)
    monkeypatch.setattr(main, "_news_rejection_reason", lambda item, now: None)
    # Main reverses selected, so oldest->newest here means newest is attempted first.
    monkeypatch.setattr(main, "_select_top_stories", lambda candidates, references: (sorted(candidates, key=lambda x: x.published), []))
    monkeypatch.setattr(main, "fetch_news_detail", lambda item: "")
    monkeypatch.setattr(main, "NEWS_PER_CYCLE", 1)
    return state_path


def test_translation_failure_does_not_starve_next_eligible_story(tmp_path, monkeypatch):
    older = _item("older", 1, "Older Iran update")
    newest = _item("newest", 2, "Newest Iran update")
    state_path = _prepare(tmp_path, monkeypatch, [older, newest])

    def translate(text):
        return "" if text.startswith("Newest") else "خبر فارسی معتبر درباره ایران"

    monkeypatch.setattr(main, "translate_to_fa", translate)
    monkeypatch.setattr(main, "format_news", lambda item, title, summary, marker_override=None: f"SEND:{item.key}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    assert main.run(datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)) == 0
    assert sent == ["SEND:older"]
    state = main.load_state(state_path)
    assert "older" in state["news_seen"]
    assert "newest" not in state["news_seen"]


def test_only_one_successful_news_item_is_sent_per_cycle(tmp_path, monkeypatch):
    older = _item("older", 1, "Older Iran update")
    newest = _item("newest", 2, "Newest Iran update")
    state_path = _prepare(tmp_path, monkeypatch, [older, newest])

    monkeypatch.setattr(main, "translate_to_fa", lambda text: "خبر فارسی معتبر درباره ایران")
    monkeypatch.setattr(main, "format_news", lambda item, title, summary, marker_override=None: f"SEND:{item.key}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    assert main.run(datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)) == 0
    assert sent == ["SEND:newest"]
    state = main.load_state(state_path)
    assert "newest" in state["news_seen"]
    assert "older" not in state["news_seen"]


def test_empty_formatter_output_is_not_marked_seen_and_queue_continues(tmp_path, monkeypatch):
    older = _item("older", 1, "Older Iran update")
    newest = _item("newest", 2, "Newest Iran update")
    state_path = _prepare(tmp_path, monkeypatch, [older, newest])

    monkeypatch.setattr(main, "translate_to_fa", lambda text: "خبر فارسی معتبر درباره ایران")
    monkeypatch.setattr(
        main,
        "format_news",
        lambda item, title, summary, marker_override=None: "" if item.key == "newest" else f"SEND:{item.key}",
    )
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    assert main.run(datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)) == 0
    assert sent == ["SEND:older"]
    state = main.load_state(state_path)
    assert "older" in state["news_seen"]
    assert "newest" not in state["news_seen"]
