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
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("12", "", "US tax cuts", "https://truth/12"), TruthPost("11", "", "Iran and Hormuz", "https://truth/11"), TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    rc = main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert len(sent) == 1
    assert "Iran and Hormuz" in sent[0]
    assert main.load_state(state_path)["truth_last_id"] == "12"


def test_subsequent_run_sends_only_new_news_and_market_not_due(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["a"],"market_last_sent_at":"2026-09-04T11:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [NewsItem("b", "Al Jazeera", "Iran attack", "new summary", "https://news/b", "Fri, 04 Sep 2026 10:00:00 GMT"), NewsItem("a", "Axios", "Iran strike", "old", "https://news/a", "Fri, 04 Sep 2026 09:00:00 GMT")])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    rc = main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert len(sent) == 1
    assert "الجزیره:" in sent[0]


def test_old_news_is_rejected_even_if_never_seen(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["seed"],"market_last_sent_at":"2026-09-04T11:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [NewsItem("old-key", "Axios", "Iran old report", "old summary", "https://news/old", "Mon, 02 Feb 2026 10:00:00 GMT"), NewsItem("today-key", "Reuters", "Iran launches missiles at US base in Qatar", "Missile attack confirmed", "https://news/today", "Fri, 04 Sep 2026 08:30:00 GMT")])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    rc = main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert len(sent) == 1
    assert "launches missiles" in sent[0]


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
    assert main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)) == 0
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
    assert main.run(datetime(2026, 9, 4, 22, 0, tzinfo=timezone.utc)) == 0
    assert sent == []


def test_semantic_duplicate_from_another_source_is_not_sent(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["reuters-original"],"market_last_sent_at":"2026-09-04T15:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [NewsItem("reuters-original", "Reuters", "Vance says Iran conflict is not a war but stops short of offering a timeline for its end", "The vice president declined to give a timeline for ending the Iran conflict.", "https://news/reuters", "Fri, 04 Sep 2026 15:20:00 GMT"), NewsItem("cnn-duplicate", "CNN", "JD Vance says Iran war has no timetable for ending", "Vance said the US would not provide a timeline for the end of the conflict with Iran.", "https://news/cnn", "Fri, 04 Sep 2026 15:35:00 GMT")])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    assert main.run(datetime(2026, 9, 4, 16, 0, tzinfo=timezone.utc)) == 0
    assert sent == []
    assert "cnn-duplicate" in main.load_state(state_path)["news_seen"]


def test_one_interview_yields_only_highest_value_headline():
    items = [
        NewsItem("v1", "CNN", "JD Vance says Iran conflict is not a war", "Vance interview", "https://n/1", "Fri, 04 Sep 2026 15:10:00 GMT"),
        NewsItem("v2", "Reuters", "Vance says US will impose new Iran sanctions", "Vance interview", "https://n/2", "Fri, 04 Sep 2026 15:15:00 GMT"),
        NewsItem("v3", "BBC News", "Vance says no timetable for Iran conflict", "Vance interview", "https://n/3", "Fri, 04 Sep 2026 15:20:00 GMT"),
    ]
    selected, skipped = main._select_top_stories(items, [])
    assert [item.key for item in selected] == ["v2"]
    assert {item.key for item in skipped} == {"v1", "v3"}


def test_military_event_outranks_interview_headlines():
    missile = NewsItem("m1", "Reuters", "Iran launches missile at target in Qatar", "Strike confirmed", "https://n/m", "Fri, 04 Sep 2026 15:25:00 GMT")
    interview = NewsItem("v1", "CNN", "JD Vance says Iran conflict is not a war", "Vance interview", "https://n/v", "Fri, 04 Sep 2026 15:30:00 GMT")
    selected, _ = main._select_top_stories([interview, missile], [])
    assert selected[0].key == "m1"
    assert main._event_priority(missile) > main._event_priority(interview)


def test_news_posts_alternate_red_and_white_across_successful_sends(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["seed"],"market_last_sent_at":"2026-09-04T15:00:00+00:00","next_news_color":"red"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [
        NewsItem("n1", "Reuters", "Iran launches missile at target in Qatar", "Strike confirmed", "https://n/1", "Fri, 04 Sep 2026 15:25:00 GMT"),
        NewsItem("n2", "Al Jazeera", "Iran and US resume nuclear talks", "Talks resumed in Geneva", "https://n/2", "Fri, 04 Sep 2026 15:30:00 GMT"),
    ])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: text)
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    assert main.run(datetime(2026, 9, 4, 16, 0, tzinfo=timezone.utc)) == 0
    news = [text for text in sent if "لینک منبع خبر" in text]
    assert len(news) == 2
    assert news[0].splitlines()[0].startswith(("🛑 ", "🔺 ", "🟥 "))
    assert news[1].splitlines()[0].startswith("⚪️ ")
    assert main.load_state(state_path)["next_news_color"] == "red"


def test_polling_iteration_sends_story_that_appears_on_next_cycle(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["seed"],"market_last_sent_at":"2026-09-04T11:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    cycles = [[], [NewsItem("m-new", "Reuters", "Iran launches missile at US base in Qatar", "Attack confirmed by officials", "https://news/m", "Fri, 04 Sep 2026 12:01:00 GMT")]]
    monkeypatch.setattr(main, "fetch_news_items", lambda: cycles.pop(0))
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: text)
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    assert main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)) == 0
    assert sent == []
    assert main.run(datetime(2026, 9, 4, 12, 2, tzinfo=timezone.utc)) == 0
    assert len(sent) == 1
    assert "launches missile" in sent[0]
    assert "m-new" in main.load_state(state_path)["news_seen"]


def test_more_than_eight_new_military_stories_are_not_held_for_later(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["seed"],"market_last_sent_at":"2026-09-04T11:00:00+00:00"}', encoding="utf-8")
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    headlines = [
        "Iran launches missile at Doha airport",
        "Iranian drone strikes naval base in Bahrain",
        "Explosion reported after Iran attack on military depot in Iraq",
        "Iran fires rockets toward US facility in Kuwait",
        "Air defense activated in Jordan after Iranian missile warning",
        "Iran drone attack damages radar site in Saudi Arabia",
        "Iran strikes command center near Abu Dhabi",
        "Missile interception reported over Qatar after Iran launch",
        "Iran attack triggers sirens at Gulf military installation",
    ]
    items = [NewsItem(f"m{i}", "Reuters", headline, f"Officials confirm event number {i}", f"https://news/{i}", f"Fri, 04 Sep 2026 12:{i:02d}:00 GMT") for i, headline in enumerate(headlines)]
    monkeypatch.setattr(main, "fetch_news_items", lambda: items)
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: (_ for _ in ()).throw(AssertionError("market should not run")))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: text)
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    assert main.run(datetime(2026, 9, 4, 12, 20, tzinfo=timezone.utc)) == 0
    assert len([text for text in sent if "لینک منبع خبر" in text]) == 9


def test_monitor_loop_runs_repeated_cycles_without_waiting_for_next_workflow(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "run", lambda now=None: calls.append(now) or 0)
    times = iter([0.0, 0.0, 60.0, 60.0, 120.0, 120.0, 181.0])
    monkeypatch.setattr(main.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)
    assert main.monitor_loop(poll_seconds=60, session_seconds=180) == 0
    assert len(calls) == 3
