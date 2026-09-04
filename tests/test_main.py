from datetime import datetime, timezone

import src.main as main
from src.sources import MarketSnapshot, NewsItem, TruthPost


def test_first_run_bootstraps_news_and_truth_but_sends_market(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "Iran talks", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [NewsItem("a", "Axios", "Iran strike", "summary", "https://news/a", "Fri, 04 Sep 2026 10:00:00 GMT")])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: MarketSnapshot(2_000_000, 200_000_000))
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")

    rc = main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert len(sent) == 1
    assert "دلار آزاد" in sent[0]
    state = main.load_state(state_path)
    assert state["truth_last_id"] == "10"
    assert state["news_seen"] == ["a"]


def test_truth_advances_state_but_sends_only_iran_related_posts(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":[],"market_last_sent_at":"2026-09-04T11:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [
        TruthPost("12", "", "US tax cuts", "https://truth/12"),
        TruthPost("11", "", "Iran and Hormuz", "https://truth/11"),
        TruthPost("10", "", "old", "https://truth/10"),
    ])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    rc = main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert len(sent) == 1
    assert "Iran and Hormuz" in sent[0]
    state = main.load_state(state_path)
    assert state["truth_last_id"] == "12"


def test_subsequent_run_sends_only_new_news_and_market_not_due(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["a"],"market_last_sent_at":"2026-09-04T11:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [
        NewsItem("b", "Al Jazeera", "Iran attack", "new summary", "https://news/b", "Fri, 04 Sep 2026 10:00:00 GMT"),
        NewsItem("a", "Axios", "Iran strike", "old", "https://news/a", "Fri, 04 Sep 2026 09:00:00 GMT"),
    ])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    rc = main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert len(sent) == 1
    assert "Al Jazeera" in sent[0]
    assert "Iran attack" in sent[0]


def test_old_news_is_rejected_even_if_never_seen(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["seed"],"market_last_sent_at":"2026-09-04T11:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [
        NewsItem("old-key", "Axios", "Iran old report", "old summary", "https://news/old", "Mon, 02 Feb 2026 10:00:00 GMT"),
        NewsItem("today-key", "Reuters", "Iran fresh report", "fresh summary", "https://news/today", "Fri, 04 Sep 2026 08:30:00 GMT"),
    ])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    rc = main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert len(sent) == 1
    assert "fresh report" in sent[0]
    assert "old report" not in sent[0]


def test_news_without_valid_publish_time_is_not_sent(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["seed"],"market_last_sent_at":"2026-09-04T11:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [NewsItem("unknown", "Reuters", "Iran undated", "summary", "https://news/u", "")])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    rc = main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert sent == []


def test_market_is_suppressed_from_midnight_until_8am_tehran(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["seed"],"market_last_sent_at":"2026-09-04T15:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market must be quiet overnight")))
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    # 01:30 Tehran (UTC+3:30 in September 2026)
    rc = main.run(datetime(2026, 9, 4, 22, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert sent == []


def test_semantic_duplicate_from_another_source_is_not_sent(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["reuters-original"],"market_last_sent_at":"2026-09-04T15:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [
        NewsItem(
            "reuters-original", "Reuters",
            "Vance says Iran conflict is not a war but stops short of offering a timeline for its end",
            "The vice president declined to give a timeline for ending the Iran conflict.",
            "https://news/reuters", "Fri, 04 Sep 2026 15:20:00 GMT",
        ),
        NewsItem(
            "cnn-duplicate", "CNN",
            "JD Vance says Iran war has no timetable for ending",
            "Vance said the US would not provide a timeline for the end of the conflict with Iran.",
            "https://news/cnn", "Fri, 04 Sep 2026 15:35:00 GMT",
        ),
    ])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))

    rc = main.run(datetime(2026, 9, 4, 16, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert sent == []
    state = main.load_state(state_path)
    assert "cnn-duplicate" in state["news_seen"]
