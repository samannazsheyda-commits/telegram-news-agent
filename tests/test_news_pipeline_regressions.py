import json
from datetime import datetime, timezone

import src.main as main
from src.sources import NewsItem, TruthPost


def _state(path):
    path.write_text(
        json.dumps(
            {
                "truth_last_id": "10",
                "news_seen": ["seed"],
                "market_last_sent_at": "2026-09-04T18:30:00+00:00",
                "car_last_sent_date": "2026-09-04",
                "weather_noon_last_sent_date": "2026-09-04",
                "weather_night_last_sent_date": "2026-09-04",
            }
        ),
        encoding="utf-8",
    )


def _wire(monkeypatch, state_path, items, sent):
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: items)
    monkeypatch.setattr(main, "fetch_news_detail", lambda item: item.summary)
    monkeypatch.setattr(main, "translate_to_fa", lambda text: text)
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))


def test_trusted_factual_iran_report_is_not_dropped_for_missing_keyword(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    _state(state_path)
    item = NewsItem(
        "nyt-intel",
        "The New York Times",
        "US intelligence assessment finds Iran prepared for a prolonged conflict",
        "The assessment says Iranian leaders are preparing for a longer confrontation.",
        "https://news/nyt",
        "Fri, 04 Sep 2026 18:30:00 GMT",
    )
    sent = []
    _wire(monkeypatch, state_path, [item], sent)

    assert main.run(datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc)) == 0
    news = [text for text in sent if "لینک منبع خبر" in text]
    assert len(news) == 1
    assert "nyt-intel" in main.load_state(state_path)["news_seen"]


def test_recent_pre_midnight_story_is_not_dropped_after_tehran_midnight(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    _state(state_path)
    item = NewsItem(
        "ap-midnight",
        "Associated Press",
        "Trump calls Iran conflict small potatoes after new remarks",
        "Trump discussed the Iran conflict in new remarks.",
        "https://news/ap-midnight",
        "Fri, 04 Sep 2026 20:21:00 GMT",
    )
    sent = []
    _wire(monkeypatch, state_path, [item], sent)

    # 21:10 UTC is 00:40 in Tehran on Sep 5; the story is only 49 minutes old.
    assert main.run(datetime(2026, 9, 4, 21, 10, tzinfo=timezone.utc)) == 0
    news = [text for text in sent if "لینک منبع خبر" in text]
    assert len(news) == 1
    assert "ap-midnight" in main.load_state(state_path)["news_seen"]


def test_rejected_news_keeps_human_readable_audit_record(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    _state(state_path)
    item = NewsItem(
        "analysis-1",
        "Reuters",
        "Analysis: Why Iran policy could reshape the region",
        "A commentary-style background article.",
        "https://news/analysis",
        "Fri, 04 Sep 2026 18:35:00 GMT",
    )
    sent = []
    _wire(monkeypatch, state_path, [item], sent)

    assert main.run(datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc)) == 0
    state = main.load_state(state_path)
    records = state.get("news_rejections") or []
    assert records
    record = records[0]
    assert record["key"] == "analysis-1"
    assert record["source"] == "Reuters"
    assert record["title"].startswith("Analysis:")
    assert record["reason"] == "article_or_commentary"


def test_low_signal_rejection_is_audited_instead_of_disappearing_silently(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    _state(state_path)
    item = NewsItem(
        "low-1",
        "Unknown Source",
        "Iran situation develops during the day",
        "No concrete event is reported.",
        "https://news/low",
        "Fri, 04 Sep 2026 18:40:00 GMT",
    )
    sent = []
    _wire(monkeypatch, state_path, [item], sent)

    assert main.run(datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc)) == 0
    state = main.load_state(state_path)
    records = state.get("news_rejections") or []
    assert sent == []
    assert any(r["key"] == "low-1" and r["reason"] == "low_signal_or_unapproved_source" for r in records)


def test_semantic_duplicate_is_audited_with_title_and_source(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    _state(state_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["news_seen"] = ["original"]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    original = NewsItem(
        "original",
        "Reuters",
        "Iran launches missile at US base in Qatar",
        "Officials confirm an Iranian missile attack on the base.",
        "https://news/original",
        "Fri, 04 Sep 2026 18:20:00 GMT",
    )
    duplicate = NewsItem(
        "duplicate",
        "CNN",
        "Iran launches missile at US base in Qatar",
        "Officials confirm an Iranian missile attack on the base.",
        "https://news/duplicate",
        "Fri, 04 Sep 2026 18:45:00 GMT",
    )
    sent = []
    _wire(monkeypatch, state_path, [original, duplicate], sent)

    assert main.run(datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc)) == 0
    records = main.load_state(state_path).get("news_rejections") or []
    assert any(
        r["key"] == "duplicate"
        and r["source"] == "CNN"
        and r["title"].startswith("Iran launches missile")
        and r["reason"] == "duplicate_or_redundant"
        for r in records
    )


def test_rejected_analysis_does_not_become_duplicate_reference_for_valid_story(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    _state(state_path)
    analysis = NewsItem(
        "analysis",
        "Reuters",
        "Analysis: Iran missile attack on Qatar base and what it means",
        "Iran missile attack on Qatar base was confirmed by officials.",
        "https://news/analysis",
        "Fri, 04 Sep 2026 18:35:00 GMT",
    )
    factual = NewsItem(
        "factual",
        "CNN",
        "Iran missile attack hits Qatar base, officials say",
        "Iran missile attack on Qatar base was confirmed by officials.",
        "https://news/factual",
        "Fri, 04 Sep 2026 18:40:00 GMT",
    )
    sent = []
    _wire(monkeypatch, state_path, [analysis, factual], sent)

    assert main.run(datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc)) == 0
    news = [text for text in sent if "لینک منبع خبر" in text]
    assert len(news) == 1
    assert "CNN:" in news[0] or "سی‌ان‌ان:" in news[0]
    assert "factual" in main.load_state(state_path)["news_seen"]
